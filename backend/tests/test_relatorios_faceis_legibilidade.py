"""Regressao de leitura e cabecalhos dos relatorios faceis em A4."""

from base64 import b64encode
from io import BytesIO
from os import getenv
from pathlib import Path
from types import SimpleNamespace as Item

from pypdf import PdfReader
from starlette.templating import Jinja2Templates
from weasyprint import HTML

from paths import TEMPLATES_DIR
from routers.exportacoes import _contexto_relatorio


TEMPLATES = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _simbolo(cor: str, letra: str) -> str:
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="90" height="90">'
        f'<circle cx="45" cy="45" r="42" fill="{cor}"/>'
        f'<text x="45" y="59" text-anchor="middle" fill="white" font-size="42">{letra}</text>'
        '</svg>'
    )
    return "data:image/svg+xml;base64," + b64encode(svg.encode()).decode()


def _base() -> dict:
    return {
        "identidade": {
            "cor_principal": "#d10b14",
            "cor_principal_escura": "#a00812",
            "texto_sobre_principal": "#ffffff",
            "logo_principal": _simbolo("#d10b14", "C"),
        },
        "simbolo_adversario": _simbolo("#112e46", "R"),
        "orientacao": "retrato",
        "alvo_nome": "Rivals BC",
        "data_exportacao": "03/10/2026",
        "equipa": Item(nome="CBQueluz"),
    }


def _pdf(template: str, contexto: dict):
    html = TEMPLATES.get_template(template).render(contexto)
    assert html.count('class="scouting-report-logo"') == 2
    assert html.count('src="data:image/svg+xml;base64,') >= 2
    pdf = HTML(string=html).write_pdf()
    destino = getenv("ROSTER_QA_PDF" if template.endswith("roster_facil.html") else "PLANO_QA_PDF")
    if destino:
        Path(destino).write_bytes(pdf)
    return html, PdfReader(BytesIO(pdf)).pages


def test_roster_facil_usa_cabecalho_simples_e_linhas_legiveis():
    contexto = _base()
    atletas = [
        Item(
            id=indice, nome=nome, numero=str(indice), posicao_principal="Extremo",
            posicao_alternativa="Base", altura_cm=190, mao_dominante="Direita",
            observacoes="Boa leitura do jogo", media_epoca=Item(pontos=12.5, assistencias=4.1, ress_total=5.2),
        )
        for indice, nome in enumerate(("Ana Martins", "Beatriz Silva", "Carla Lopes"), 1)
    ]
    contexto.update(
        atletas=atletas, fotografias={}, secoes_set={"notas", "estatisticas"},
        stat_fields=["pontos", "assistencias", "ress_total"],
        stat_labels={"pontos": "Pontos", "assistencias": "Assistências", "ress_total": "Ressaltos"},
    )
    html, paginas = _pdf("relatorios/roster_facil.html", contexto)
    assert "Roster - Rivals BC" in html
    assert len(paginas) == 1
    texto = " ".join(paginas[0].extract_text().split())
    for valor in ("Roster - Rivals BC", "Ana Martins", "Beatriz Silva", "Carla Lopes", "Assistências"):
        assert valor in texto


def test_plano_de_jogo_facil_usa_o_simbolo_do_adversario_e_titulo_curto():
    contexto = _base()
    contexto.update(
        jogo=Item(adversario="Rivals BC", data="03/10/2026", hora="15:00", local="Pavilhao Central", competicao="Liga"),
        secoes_set={"dados_jogo"}, plano=None, titulares=[], cinco_adversario=[], convocados=[],
        rotacoes_equipa={}, graficos_plano=[], fotografias_equipa={}, fotografias_adversario={},
    )
    html, paginas = _pdf("relatorios/plano_jogo_facil.html", contexto)
    assert "Plano de jogo - Rivals BC" in html
    assert len(paginas) == 1
    assert "Plano de jogo - Rivals BC" in paginas[0].extract_text()


def test_roster_longo_nao_divide_a_identificacao_e_as_notas_do_jogador():
    contexto = _base()
    contexto.update(
        atletas=[
            Item(
                id=numero, nome=f"Atleta {numero:02d}", numero=str(numero),
                posicao_principal="Base", posicao_alternativa=None, altura_cm=180,
                mao_dominante="Direita", observacoes=f"Nota exclusiva {numero:02d}",
                media_epoca=Item(pontos=numero * 1.0),
            )
            for numero in range(1, 13)
        ],
        fotografias={}, secoes_set={"notas", "estatisticas"},
        stat_fields=["pontos"], stat_labels={"pontos": "Pontos"},
    )
    _, paginas = _pdf("relatorios/roster_facil.html", contexto)
    assert len(paginas) >= 2
    textos = [" ".join(pagina.extract_text().split()) for pagina in paginas]
    for numero in range(1, 13):
        assert any(f"Atleta {numero:02d}" in texto and f"Nota exclusiva {numero:02d}" in texto for texto in textos)


def test_contexto_de_exportacao_prepara_o_simbolo_nos_dois_relatorios(monkeypatch):
    monkeypatch.setattr("routers.exportacoes._fotografia_embebida", lambda url: f"embebido:{url}" if url else None)
    dados = Item(getlist=lambda chave: [])
    adversario = Item(simbolo="rivals.png", jogadores=[], rotacao_prevista=[], itens_coletivos=[])
    equipa = Item(nome="CBQueluz")
    roster = _contexto_relatorio("roster", adversario, equipa, dados, None)
    assert roster["simbolo_adversario"] == "embebido:rivals.png"

    class Consulta:
        def filter(self, *args):
            return self

        def first(self):
            return Item(adversario=adversario)

    jogo = Item(id=1, plano=None, convocados=[])
    db = Item(query=lambda modelo: Consulta())
    plano = _contexto_relatorio("plano-jogo", jogo, equipa, dados, db)
    assert plano["simbolo_adversario"] == "embebido:rivals.png"

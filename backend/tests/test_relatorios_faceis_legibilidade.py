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
from routers.exportacoes import _contexto_relatorio, _simbolo_embebido


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


def test_plano_facil_destaca_chaves_e_defesas_sem_convocados():
    contexto = _base()
    contexto["identidade"]["cor_secundaria"] = "#ffffff"
    jogadores = [
        Item(id=indice, nome=f"Atleta {indice}", numero_camisola=indice, posicao="Base")
        for indice in range(1, 6)
    ]
    contexto.update(
        jogo=Item(adversario="Rivals BC", data="04/10/2026", hora="15:00", local="Pavilhão", competicao="Liga"),
        secoes_set={"dados_jogo", "convocatoria", "plano_ofensivo", "plano_defensivo", "cinco_previsto"},
        plano=Item(reflexao=None), titulares=jogadores,
        convocados=[Item(jogador=Item(nome="Convocado não selecionado"))],
        cinco_adversario=[], rotacoes_equipa={}, graficos_plano=[], fotografias_adversario={},
        fotografias_equipa={j.id: _simbolo("#d10b14", str(j.id)) for j in jogadores[:4]},
        conteudo_plano={
            "chave_ataque": ["Explorar vantagem no primeiro passe"],
            "chave_defesa": ["Fechar a linha central"],
            "bloqueio_direto_lateral": ["Forçar para a linha lateral"],
            "bloqueio_direto_central": ["Mostrar cobertura alta"],
            "handoff": ["Trocar com comunicação"],
            "indiretos_entrada": ["Perseguir e recuperar"],
            "indiretos_saida": ["Negar receção"],
            "bola_dentro": ["Ajudar do lado fraco"],
        },
    )
    html, paginas = _pdf("relatorios/plano_jogo_facil.html", contexto)
    texto = " ".join(pagina.extract_text() for pagina in paginas)

    for valor in ("Chaves do jogo", "Explorar vantagem no primeiro passe", "Fechar a linha central",
                  "Estratégias defensivas por situação", "Bloqueio direto lateral", "Forçar para a linha lateral",
                  "Handoff", "Trocar com comunicação", "Bloqueio direto central", "Mostrar cobertura alta",
                  "Indiretos de entrada", "Perseguir e recuperar", "Indiretos de saída", "Negar receção",
                  "Bola dentro", "Ajudar do lado fraco"):
        assert valor in texto
    assert "Convocado não selecionado" not in html
    assert "object-fit:contain" in html
    assert 'class="easy-avatar"' in html


def test_plano_facil_reserva_as_ultimas_paginas_para_jogadas():
    contexto = _base()
    contexto.update(
        jogo=Item(adversario="Rivals BC", data="04/10/2026", hora=None, local=None, competicao=None),
        secoes_set={"dados_jogo", "plano_ofensivo"}, plano=None,
        titulares=[], cinco_adversario=[], rotacoes_equipa={},
        fotografias_equipa={}, fotografias_adversario={},
        conteudo_plano={"chave_ataque": ["Chave prioritária antes do Playbook"]},
        graficos_plano=[
            Item(imagem=_simbolo("#d10b14", str(indice)), titulo=f"Jogada {indice:02d}", passo=1, observacao=None)
            for indice in range(1, 17)
        ],
    )

    _, paginas = _pdf("relatorios/plano_jogo_facil.html", contexto)
    textos = [pagina.extract_text() for pagina in paginas]

    assert len(paginas) >= 3
    assert "Chave prioritária antes do Playbook" in textos[0]
    assert "Jogadas do plano" not in textos[0]
    assert "Jogadas do plano" in textos[1]
    assert "Jogada 01" in textos[1]
    assert "Jogadas do plano" in textos[-1]
    assert "continuação" in textos[-1]
    assert "Jogada 16" in textos[-1]
    assert all("Chave prioritária antes do Playbook" not in texto for texto in textos[1:])

    contexto["orientacao"] = "paisagem"
    _, paginas_paisagem = _pdf("relatorios/plano_jogo_facil.html", contexto)
    textos_paisagem = [pagina.extract_text() for pagina in paginas_paisagem]
    assert len(paginas_paisagem) >= 4
    assert "Jogadas do plano" not in textos_paisagem[0]
    assert all("Jogadas do plano" in texto for texto in textos_paisagem[1:])
    assert "Jogada 16" in textos_paisagem[-1]


def test_plano_facil_omite_defesas_nao_preenchidas_ou_deselecionadas():
    contexto = _base()
    contexto.update(
        jogo=Item(adversario="Rivals BC", data="04/10/2026", hora=None, local=None, competicao=None),
        secoes_set={"plano_ofensivo"}, plano=None, titulares=[], cinco_adversario=[],
        rotacoes_equipa={}, graficos_plano=[], fotografias_equipa={}, fotografias_adversario={},
        conteudo_plano={"chave_ataque": ["Atacar o lado fraco"], "handoff": ["Trocar"]},
    )
    html = TEMPLATES.get_template("relatorios/plano_jogo_facil.html").render(contexto)

    assert "Atacar o lado fraco" in html
    assert "Estratégias defensivas por situação" not in html
    assert "Trocar" not in html


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
    monkeypatch.setattr("routers.exportacoes._simbolo_embebido", lambda url: f"embebido:{url}" if url else None)
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


def test_simbolo_de_adversario_aceita_pasta_de_branding(monkeypatch, tmp_path):
    imagem = tmp_path / "rivals.png"
    imagem.write_bytes(b"simbolo")
    monkeypatch.setattr("routers.exportacoes.caminho_logo_guardado", lambda url: imagem)

    assert _simbolo_embebido("/static/uploads/branding/rivals.png") == "data:image/png;base64,c2ltYm9sbw=="

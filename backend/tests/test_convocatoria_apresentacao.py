from base64 import b64encode
from datetime import date
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

from pypdf import PdfReader
from weasyprint import HTML

from paths import TEMPLATES_DIR
from routers import jogos as jogos_router
from template_config import Jinja2Templates


def test_convocatoria_tem_edicao_reforcos_e_limite_de_doze_atletas():
    raiz = Path(__file__).resolve().parents[2]
    detalhe = (raiz / "frontend/templates/jogos/detalhe.html").read_text(encoding="utf-8")
    router = (raiz / "backend/routers/jogos.py").read_text(encoding="utf-8")

    assert "Editar convocatória" in detalhe
    assert "Escalão imediatamente abaixo" in detalhe
    assert "jogador.equipa_id != jogo.equipa_id" in detalhe
    assert "excede_limite = len(jogadores_ids) > 12" in router
    assert "jogadores_ids = jogadores_ids[:12]" in router


def test_documento_da_convocatoria_numera_a_lista_e_lista_observacoes():
    raiz = Path(__file__).resolve().parents[2]
    documento = (raiz / "frontend/templates/jogos/convocatoria_print.html").read_text(encoding="utf-8")

    assert "{{ loop.index }}" in documento
    assert "jogadores_convocados[:12]" in documento
    assert "observacoes.splitlines()" in documento
    assert "nome_clube ~ ' · Convocatória'" in documento


def test_convocatoria_pdf_usa_cabecalho_uniforme_sem_perder_dados():
    def simbolo(cor):
        svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20"><circle cx="10" cy="10" r="9" fill="{cor}"/></svg>'
        return "data:image/svg+xml;base64," + b64encode(svg.encode()).decode()

    clube = SimpleNamespace(nome="CBQueluz", genero="masculino", treinadores=[])
    convocados = [SimpleNamespace(hora_encontro="13:00", local_encontro="Pavilhão", observacoes="Levar equipamento")]
    jogo = SimpleNamespace(
        id=1, adversario="Rivals BC", data=date(2026, 10, 3), hora="15:00",
        local="Pavilhão Central", competicao="Liga", em_casa=True,
        equipa=clube, convocados=convocados,
    )
    contexto = {
        "identidade": {
            "cor_principal": "#b90000", "texto_sobre_principal": "#ffffff",
            "logo_principal": simbolo("red"),
        },
        "simbolo_adversario": simbolo("navy"),
        "jogo": jogo,
        "jogadores_convocados": [SimpleNamespace(nome="Ana Martins")],
        "nome_clube": "CBQueluz",
        "modo_pdf": True,
    }
    html = Jinja2Templates(directory=str(TEMPLATES_DIR)).get_template("jogos/convocatoria_print.html").render(contexto)

    assert "Convocatória - Rivals BC" in html
    assert html.count('class="scouting-report-logo"') == 2
    assert html.count('src="data:image/svg+xml;base64,') == 2
    paginas = PdfReader(BytesIO(HTML(string=html).write_pdf())).pages
    assert len(paginas) == 1
    texto = paginas[0].extract_text()
    for valor in ("Convocatória - Rivals BC", "Ana Martins", "Levar equipamento", "13:00"):
        assert valor in texto


def test_contexto_convocatoria_usa_simbolo_do_adversario_associado(monkeypatch, tmp_path):
    ficheiro = tmp_path / "simbolo.png"
    ficheiro.write_bytes(b"imagem")
    ligacao = SimpleNamespace(adversario=SimpleNamespace(simbolo="/static/uploads/branding/simbolo.png"))
    consulta = SimpleNamespace(filter=lambda _: SimpleNamespace(first=lambda: ligacao))
    db = SimpleNamespace(query=lambda _: consulta)
    request = SimpleNamespace(state=SimpleNamespace(identidade_clube={}))
    jogo = SimpleNamespace(id=1, equipa=SimpleNamespace(nome="CBQueluz"), convocados=[])
    monkeypatch.setattr(
        jogos_router, "caminho_logo_guardado",
        lambda url: ficheiro if url == ligacao.adversario.simbolo else None,
    )
    monkeypatch.setattr(jogos_router, "imagem_estatica_data_uri", lambda caminho, mime: f"{caminho.name}:{mime}")

    contexto = jogos_router._contexto_convocatoria(request, db, jogo, SimpleNamespace())

    assert contexto["simbolo_adversario"] == "simbolo.png:image/png"
    assert contexto["nome_clube"] == "CBQueluz"

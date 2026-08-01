import pytest
from io import BytesIO
import re

from pypdf import PdfReader

from models.planeamento import Mesociclo, Microciclo, SessaoTreino
from database import SessionLocal
from paths import TEMPLATES_DIR

from routers.treino import _normalizar_bloco, _normalizar_minutos


def test_identidade_do_clube_abre_para_coordenacao(client_coordenador):
    resposta = client_coordenador.get("/administracao/identidade")

    assert resposta.status_code == 200
    assert "Identidade do clube" in resposta.text
    assert "/static/css/design-system.css" in resposta.text


def test_validadores_do_plano_de_treino_rejeitam_dados_ambiguos():
    assert _normalizar_minutos("15") == 15
    assert _normalizar_bloco(" b ") == "B"

    with pytest.raises(ValueError, match="entre 1 e 240"):
        _normalizar_minutos("0")
    with pytest.raises(ValueError, match="A, B, C ou D"):
        _normalizar_bloco("E")


def test_templates_pdf_declaram_a4_e_branding_comum():
    templates = sorted(
        caminho
        for caminho in TEMPLATES_DIR.rglob("*.html")
        if ("pdf" in caminho.name.lower() or "print" in caminho.name.lower())
        and "partials" not in caminho.parts
    )

    assert len(templates) >= 17
    for caminho in templates:
        conteudo = caminho.read_text(encoding="utf-8")
        assert re.search(r"size\s*:\s*A4", conteudo, flags=re.IGNORECASE), caminho
        assert "partials/pdf_branding.html" in conteudo, caminho


def test_exportacoes_de_planeamento_e_treino_geram_pdf_a4(client_admin):
    from test_fase2_assiduidade_evolucao import _criar_contexto, _limpar_contexto

    db, equipa_id, jogadora_id, segunda_jogadora_id, macro_id = _criar_contexto()
    meso = db.query(Mesociclo).filter(Mesociclo.macrociclo_id == macro_id).first()
    micro = db.query(Microciclo).filter(Microciclo.mesociclo_id == meso.id).first()
    sessao = db.query(SessaoTreino).filter(SessaoTreino.microciclo_id == micro.id).first()

    try:
        rotas = [
            f"/planeamento/macrociclos/{macro_id}/pdf",
            f"/planeamento/mesociclos/{meso.id}/pdf",
            f"/planeamento/microciclos/{micro.id}/calendario/pdf",
            f"/planeamento/microciclos/{micro.id}/pdf",
            f"/treino/sessoes/{sessao.id}/pdf",
        ]
        respostas = [client_admin.get(rota) for rota in rotas]
        assert all(resposta.status_code == 200 for resposta in respostas)
        assert all(resposta.content.startswith(b"%PDF") for resposta in respostas)
        caixas = [
            (float(pagina.mediabox.width), float(pagina.mediabox.height))
            for resposta in respostas
            for pagina in PdfReader(BytesIO(resposta.content)).pages
        ]
        assert any(abs(largura - 841.89) < 1 for largura, altura in caixas if altura < largura)
        assert any(abs(altura - 841.89) < 1 for largura, altura in caixas if altura > largura)
    finally:
        _limpar_contexto(db, equipa_id, jogadora_id, segunda_jogadora_id, macro_id)
        db.close()

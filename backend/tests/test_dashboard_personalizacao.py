import json
from pathlib import Path

from database import SessionLocal
from models.utilizador import Utilizador

ROOT = Path(__file__).resolve().parents[2]


def test_dashboard_permite_guardar_e_repor_blocos_visiveis(client_admin):
    db = SessionLocal()
    utilizador = db.query(Utilizador).filter(Utilizador.username == "admin").one()
    preferencias_originais = utilizador.preferencias_dashboard
    try:
        pagina = client_admin.get("/dashboard")
        assert pagina.status_code == 200
        assert "data-customizable-dashboard" in pagina.text
        assert "dashboard-customization.js" in pagina.text

        resposta = client_admin.post(
            "/dashboard/preferencias",
            json={
                "dashboard": "inicio-administrador",
                "ocultos": ["centro-de-acao", "resumo-e-indicadores"],
            },
        )
        assert resposta.status_code == 200
        assert resposta.json()["sucesso"] is True

        db.expire_all()
        preferencias = json.loads(utilizador.preferencias_dashboard)
        assert preferencias["inicio-administrador"] == [
            "centro-de-acao",
            "resumo-e-indicadores",
        ]

        resposta = client_admin.post(
            "/dashboard/preferencias",
            json={"dashboard": "inicio-administrador", "ocultos": []},
        )
        assert resposta.status_code == 200
        db.expire_all()
        preferencias = json.loads(utilizador.preferencias_dashboard or "{}")
        assert "inicio-administrador" not in preferencias
    finally:
        utilizador.preferencias_dashboard = preferencias_originais
        db.commit()
        db.close()


def test_dashboard_rejeita_chaves_de_preferencia_invalidas(client_admin):
    resposta = client_admin.post(
        "/dashboard/preferencias",
        json={"dashboard": "../../outro", "ocultos": ["bloco"]},
    )
    assert resposta.status_code == 422
    assert resposta.json()["sucesso"] is False


def test_dashboard_treinador_coloca_equipas_antes_do_centro_de_acao():
    template = (ROOT / "frontend" / "templates" / "dashboard_treinador.html").read_text(
        encoding="utf-8"
    )
    assert template.index("{% for item in dados_equipas %}") < template.index(
        'include "partials/painel_operacional_compacto.html"'
    )
    assert "data-customizable-dashboard" in template


def test_dashboards_de_questionarios_tambem_sao_personalizaveis():
    for nome in ("painel.html", "detalhe.html", "resultados.html"):
        template = (ROOT / "frontend" / "templates" / "questionarios" / nome).read_text(
            encoding="utf-8"
        )
        assert "data-customizable-dashboard" in template

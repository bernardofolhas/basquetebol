import main
from main import app
from testsupport import TestClient


def _criar_client():
    """Cria um cliente de teste isolado para cada cenário."""
    return TestClient(app)


def test_health_responde_com_200():
    client = _criar_client()

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "estado": "ok",
        "servico": "basquetebol",
        "ambiente": main.config.ambiente,
        "versao": main.VERSAO_APLICACAO,
    }


def test_ready_responde_com_200_quando_app_esta_operacional():
    client = _criar_client()

    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {
        "estado": "ok",
        "ambiente": main.config.ambiente,
        "base_dados": "ok",
    }


def test_ready_responde_com_503_quando_base_dados_falha(monkeypatch):
    client = _criar_client()

    monkeypatch.setattr(main, "base_dados_disponivel", lambda: False)

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {
        "estado": "indisponivel",
        "ambiente": main.config.ambiente,
        "base_dados": "indisponivel",
    }

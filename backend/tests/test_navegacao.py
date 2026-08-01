from main import app
from testsupport import TestClient


def _criar_client():
    """Cria um cliente de teste isolado para cada teste."""
    return TestClient(app)


def _autenticar_admin(client: TestClient):
    """
    Faz login com o utilizador administrador de testes.

    O mesmo client é reutilizado para preservar a sessão entre pedidos.
    """
    response = client.post(
        "/login-form",
        data={
            "username": "admin",
            "password": "admin123"
        },
        follow_redirects=False
    )

    assert response.status_code in [302, 303]
    assert response.headers["location"] == "/dashboard"


def test_dashboard_sem_autenticacao_redireciona_para_login():
    client = _criar_client()

    response = client.get("/dashboard", follow_redirects=False)

    assert response.status_code in [302, 307]
    assert response.headers["location"] == "/login"


def test_dashboard_com_login_responde_com_sucesso():
    client = _criar_client()
    _autenticar_admin(client)

    response = client.get("/dashboard")

    assert response.status_code == 200


def test_atividades_com_login_responde_com_sucesso():
    client = _criar_client()
    _autenticar_admin(client)

    response = client.get("/atividades")

    assert response.status_code == 200


def test_calendario_com_login_responde_com_sucesso():
    client = _criar_client()
    _autenticar_admin(client)

    response = client.get("/calendario")

    assert response.status_code == 200

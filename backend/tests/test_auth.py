from main import app
from testsupport import TestClient


def _criar_client():
    """Cria um cliente de teste isolado para cada cenário."""
    return TestClient(app)


def test_login_admin():
    client = _criar_client()
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


def test_logout_post_termina_a_sessao_com_csrf(client_admin):
    response = client_admin.post("/logout", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"
    dashboard = client_admin.get("/dashboard", follow_redirects=False)
    assert dashboard.status_code in (302, 303)

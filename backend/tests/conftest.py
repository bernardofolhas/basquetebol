"""
Fixtures partilhadas por todos os ficheiros de testes.

Centraliza a criação do cliente de teste e os helpers de autenticação,
eliminando a duplicação de _criar_client() e _autenticar_*() em cada ficheiro.
"""
import pytest
from main import app
from auth import encriptar_password
from database import SessionLocal
from limiter import limiter
from models.utilizador import Utilizador
from testsupport import TestClient

CREDENCIAIS = {
    "admin": {"username": "admin", "password": "admin123"},
    "coordenador": {"username": "coord", "password": "coord123"},
    "treinador": {"username": "coach1", "password": "coach123"},
}


@pytest.fixture(autouse=True)
def limpar_rate_limit_entre_testes():
    """Evita que o limite de login de produção torne a suite dependente da ordem."""
    limiter._storage.reset()
    yield
    limiter._storage.reset()


@pytest.fixture(autouse=True, scope="session")
def garantir_credenciais_dos_testes():
    """Mantém as contas de teste determinísticas sem alterar as passwords reais."""
    db = SessionLocal()
    credenciais = {
        "admin": "admin123",
        "coord": "coord123",
        "coach1": "coach123",
    }
    originais = {}
    estados_originais = {}
    try:
        for username, password in credenciais.items():
            utilizador = db.query(Utilizador).filter(Utilizador.username == username).first()
            if not utilizador:
                continue
            originais[username] = utilizador.password_hash
            estados_originais[username] = utilizador.ativo
            utilizador.password_hash = encriptar_password(password)
            utilizador.ativo = True
        db.commit()
    finally:
        db.close()

    yield

    db = SessionLocal()
    try:
        for username, password_hash in originais.items():
            utilizador = db.query(Utilizador).filter(Utilizador.username == username).first()
            if utilizador:
                utilizador.password_hash = password_hash
                utilizador.ativo = estados_originais[username]
        db.commit()
    finally:
        db.close()


@pytest.fixture
def client():
    """Cliente de teste isolado para cada teste."""
    return TestClient(app)


@pytest.fixture
def client_admin(client):
    """Cliente já autenticado como administrador."""
    _autenticar(client, "admin")
    return client


@pytest.fixture
def client_coordenador(client):
    """Cliente já autenticado como coordenador."""
    _autenticar(client, "coordenador")
    return client


@pytest.fixture
def client_treinador(client):
    """Cliente já autenticado como treinador."""
    _autenticar(client, "treinador")
    return client


def _autenticar(client: TestClient, perfil: str) -> None:
    """Faz login com as credenciais do perfil indicado."""
    creds = CREDENCIAIS[perfil]
    response = client.post(
        "/login-form",
        data={"username": creds["username"], "password": creds["password"]},
        follow_redirects=False,
    )
    assert response.status_code in (302, 303), (
        f"Login como '{perfil}' falhou: status {response.status_code}"
    )

from pathlib import Path
import sys

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from main import app
from testsupport import TestClient


UTILIZADORES_TESTE = {
    "admin": {"username": "admin", "password": "admin123"},
    "coordenador": {"username": "coord", "password": "coord123"},
    "treinador": {"username": "coach1", "password": "coach123"},
}

NOME_EQUIPA_TESTE = "Equipa Teste Sprint 9"
ADVERSARIO_JOGO_EQUIPA_TESTE = "Adversario Equipa Sprint 9"
NOME_TREINADOR_TESTE = "Treinador Teste Sprint 9"


def _criar_client():
    """Cria um cliente de teste isolado para cada cenário."""
    return TestClient(app)


def _fazer_login(client: TestClient, perfil: str):
    """
    Autentica um utilizador real do sistema e mantém a sessão no mesmo client.
    """
    credenciais = UTILIZADORES_TESTE[perfil]

    response = client.post(
        "/login-form",
        data=credenciais,
        follow_redirects=False
    )

    assert response.status_code in [302, 303]
    assert response.headers["location"] == "/dashboard"


def _apagar_equipa_teste():
    """
    Remove a equipa de teste caso uma falha de permissões a tenha criado.
    """
    from database import SessionLocal
    from models.equipa import Equipa
    from models.jogo import Jogo
    from models.planeamento_clube import EventoPlaneamentoClube

    db = SessionLocal()
    try:
        for evento in db.query(EventoPlaneamentoClube).filter(EventoPlaneamentoClube.titulo == NOME_EQUIPA_TESTE).all():
            db.delete(evento)
        for jogo in db.query(Jogo).filter(Jogo.adversario == ADVERSARIO_JOGO_EQUIPA_TESTE).all():
            db.delete(jogo)
        registos = db.query(Equipa).filter(Equipa.nome == NOME_EQUIPA_TESTE).all()
        for registo in registos:
            db.delete(registo)
        db.commit()
    finally:
        db.close()


def _criar_equipa_com_jogo():
    from datetime import date

    from database import SessionLocal
    from models.equipa import Equipa, EscalaoEnum, GeneroEnum
    from models.jogo import Jogo

    db = SessionLocal()
    try:
        equipa = Equipa(
            nome=NOME_EQUIPA_TESTE,
            escalao=EscalaoEnum.senior,
            genero=GeneroEnum.masculino,
            seccionista=None,
        )
        db.add(equipa)
        db.commit()
        db.refresh(equipa)

        jogo = Jogo(
            data=date.fromisoformat("2026-04-20"),
            hora="15:00",
            local="Pavilhão Municipal",
            adversario=ADVERSARIO_JOGO_EQUIPA_TESTE,
            competicao="Campeonato Nacional",
            em_casa=True,
            equipa_id=equipa.id,
        )
        db.add(jogo)
        db.commit()
        return equipa.id
    finally:
        db.close()


def _criar_equipa_com_evento_global():
    from datetime import date

    from database import SessionLocal
    from models.equipa import Equipa, EscalaoEnum, GeneroEnum
    from models.planeamento_clube import EventoPlaneamentoClube, OrigemEventoPlaneamentoClubeEnum, TipoEventoPlaneamentoClubeEnum

    db = SessionLocal()
    try:
        equipa = Equipa(
            nome=NOME_EQUIPA_TESTE,
            escalao=EscalaoEnum.senior,
            genero=GeneroEnum.masculino,
            seccionista=None,
        )
        db.add(equipa)
        db.commit()
        db.refresh(equipa)

        evento = EventoPlaneamentoClube(
            tipo=TipoEventoPlaneamentoClubeEnum.treino_equipa,
            titulo=NOME_EQUIPA_TESTE,
            data=date.fromisoformat("2026-04-21"),
            equipa_id=equipa.id,
            aplica_a_todas_equipas=False,
            origem=OrigemEventoPlaneamentoClubeEnum.manual,
        )
        evento.equipas = [equipa]
        db.add(evento)
        db.commit()
        return equipa.id
    finally:
        db.close()


def _criar_equipa_com_playbook():
    from database import SessionLocal
    from models.equipa import Equipa, EscalaoEnum, GeneroEnum
    from models.playbook import PassoSetPlay, Playbook, SetPlay

    db = SessionLocal()
    try:
        equipa = Equipa(
            nome=NOME_EQUIPA_TESTE,
            escalao=EscalaoEnum.senior,
            genero=GeneroEnum.masculino,
            seccionista=None,
        )
        db.add(equipa)
        db.flush()

        playbook = Playbook(
            equipa_id=equipa.id,
            nome="Playbook de teste",
        )
        db.add(playbook)
        db.flush()

        setplay = SetPlay(
            playbook_id=playbook.id,
            nome="Ataque de teste",
        )
        db.add(setplay)
        db.flush()
        db.add(PassoSetPlay(setplay_id=setplay.id, ordem=1, observacao="Passo de teste"))
        db.commit()
        return equipa.id
    finally:
        db.close()


def _apagar_treinador_teste():
    """
    Remove o treinador de teste caso uma falha de permissões o tenha criado.
    """
    from database import SessionLocal
    from models.treinador import Treinador

    db = SessionLocal()
    try:
        registos = db.query(Treinador).filter(Treinador.nome == NOME_TREINADOR_TESTE).all()
        for registo in registos:
            db.delete(registo)
        db.commit()
    finally:
        db.close()


@pytest.mark.parametrize("rota", ["/dashboard", "/equipas/nova", "/treinadores/novo"])
def test_utilizador_sem_login_nao_entra_em_paginas_protegidas(rota: str):
    """
    Sem sessão iniciada, as páginas protegidas devem redirecionar para o login.
    """
    client = _criar_client()

    response = client.get(rota, follow_redirects=False)

    assert response.status_code in [302, 307]
    assert response.headers["location"] == "/login"


def test_treinador_nao_consegue_aceder_a_pagina_de_administracao():
    """
    A área administrativa deve devolver 403 para um treinador autenticado.
    """
    client = _criar_client()
    _fazer_login(client, "treinador")

    response = client.get("/admin/utilizadores", follow_redirects=False)

    assert response.status_code == 403


def test_treinador_nao_consegue_criar_equipa():
    """
    Um treinador não deve conseguir abrir o formulário nem submeter a criação
    de equipas.
    """
    client = _criar_client()
    _fazer_login(client, "treinador")

    _apagar_equipa_teste()

    try:
        response_form = client.get("/equipas/nova", follow_redirects=False)
        response_post = client.post(
            "/equipas/nova",
            data={
                "nome": NOME_EQUIPA_TESTE,
                "escalao": "senior",
                "genero": "masculino",
                "seccionista": ""
            },
            follow_redirects=False
        )

        assert response_form.status_code in [302, 307]
        assert response_form.headers["location"] == "/equipas"
        assert response_post.status_code in [302, 303, 307]
        assert response_post.headers["location"] == "/equipas"
    finally:
        _apagar_equipa_teste()


def test_treinador_nao_consegue_criar_treinador():
    """
    Um treinador não deve conseguir abrir o formulário nem submeter a criação
    de outros treinadores.
    """
    client = _criar_client()
    _fazer_login(client, "treinador")

    _apagar_treinador_teste()

    try:
        response_form = client.get("/treinadores/novo", follow_redirects=False)
        response_post = client.post(
            "/treinadores/novo",
            data={
                "nome": NOME_TREINADOR_TESTE,
                "data_nascimento": "",
                "morada": "",
                "telefone": "",
                "email": "",
                "numero_cedula": "",
                "numero_fpb": "",
                "observacoes": ""
            },
            follow_redirects=False
        )

        assert response_form.status_code in [302, 307]
        assert response_form.headers["location"] == "/treinadores"
        assert response_post.status_code in [302, 303, 307]
        assert response_post.headers["location"] == "/treinadores"
    finally:
        _apagar_treinador_teste()


@pytest.mark.parametrize("rota", ["/dashboard", "/equipas/nova", "/treinadores/novo"])
def test_coordenador_consegue_aceder_as_paginas_de_gestao_permitidas(rota: str):
    """
    O coordenador deve conseguir entrar nas páginas de gestão que lhe são
    permitidas.
    """
    client = _criar_client()
    _fazer_login(client, "coordenador")

    response = client.get(rota, follow_redirects=False)

    assert response.status_code == 200


def test_administrador_consegue_aceder_a_listagem_de_utilizadores():
    """
    O administrador deve conseguir abrir a área administrativa de utilizadores.
    """
    client = _criar_client()
    _fazer_login(client, "admin")

    response = client.get("/admin/utilizadores", follow_redirects=False)

    assert response.status_code == 200


def test_administrador_consegue_apagar_equipa_com_jogos_associados():
    client = _criar_client()
    _fazer_login(client, "admin")
    _apagar_equipa_teste()

    try:
        equipa_id = _criar_equipa_com_jogo()

        response = client.post(f"/equipas/{equipa_id}/apagar", follow_redirects=False)

        assert response.status_code == 303
        assert response.headers["location"] == "/equipas"
    finally:
        _apagar_equipa_teste()


def test_administrador_consegue_apagar_equipa_com_eventos_globais_associados():
    client = _criar_client()
    _fazer_login(client, "admin")
    _apagar_equipa_teste()

    try:
        equipa_id = _criar_equipa_com_evento_global()

        response = client.post(f"/equipas/{equipa_id}/apagar", follow_redirects=False)

        assert response.status_code == 303
        assert response.headers["location"] == "/equipas"
    finally:
        _apagar_equipa_teste()


def test_administrador_consegue_apagar_equipa_com_playbook_associado():
    client = _criar_client()
    _fazer_login(client, "admin")
    _apagar_equipa_teste()

    try:
        equipa_id = _criar_equipa_com_playbook()

        response = client.post(f"/equipas/{equipa_id}/apagar", follow_redirects=False)

        assert response.status_code == 303
        assert response.headers["location"] == "/equipas"
    finally:
        _apagar_equipa_teste()

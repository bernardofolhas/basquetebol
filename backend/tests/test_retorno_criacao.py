from fastapi import FastAPI
from fastapi.responses import PlainTextResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

from middleware_retorno_criacao import (
    RetornoAposCriacaoMiddleware,
    _abre_dashboard_criado,
    _caminho_interno,
    _e_criacao,
    _e_formulario,
)
from testsupport import TestClient


def test_retorno_so_aceita_caminhos_internos():
    assert _caminho_interno("https://exemplo.pt/equipas/3?aba=plantel") == "/equipas/3?aba=plantel"
    assert _caminho_interno("//externo.pt") is None
    assert _caminho_interno("https://externo.pt") is None
    assert _caminho_interno("/planeamento/equipas/1/anuais", "/planeamento/equipas/1/anuais") is None


def test_identifica_formularios_de_criacao_e_edicao():
    assert _e_criacao("/planeamento-clube/espacos/novo")
    assert _e_criacao("/planeamento-clube/espacos/1/disponibilidades")
    assert _e_criacao("/treino/planos/2/blocos")
    assert not _e_criacao("/planeamento/microciclos/2/editar")
    assert _e_formulario("/planeamento/microciclos/2/editar")
    assert not _abre_dashboard_criado("/planeamento/equipas/1/macrociclos/novo")


def test_criacao_e_ciclos_regressam_a_origem():
    app = FastAPI()
    app.add_middleware(RetornoAposCriacaoMiddleware)
    app.add_middleware(SessionMiddleware, secret_key="teste")

    @app.get("/itens/novo")
    def form_item():
        return PlainTextResponse("formulário")

    @app.post("/itens/novo")
    def criar_item():
        return RedirectResponse("/itens/9", status_code=303)

    @app.post("/equipas/1/macrociclos/novo")
    def criar_macro():
        return RedirectResponse("/planeamento/macrociclos/8", status_code=303)

    client = TestClient(app)
    client.get("/itens/novo", headers={"referer": "http://testserver/equipas/1"})
    criado = client.post("/itens/novo", follow_redirects=False)
    macro = client.post("/equipas/1/macrociclos/novo", headers={"referer": "http://testserver/equipas/1"}, follow_redirects=False)

    assert criado.headers["location"] == "/equipas/1"
    assert macro.headers["location"] == "/equipas/1"


def test_edicao_e_eliminacao_regressam_a_pagina_de_origem():
    app = FastAPI()
    app.add_middleware(RetornoAposCriacaoMiddleware)
    app.add_middleware(SessionMiddleware, secret_key="teste")

    @app.get("/itens/4/editar")
    def editar_item():
        return PlainTextResponse("formulário")

    @app.post("/itens/4/editar")
    def guardar_item():
        return RedirectResponse("/itens/4", status_code=303)

    @app.post("/itens/4/eliminar")
    def eliminar_item():
        return RedirectResponse("/itens", status_code=303)

    client = TestClient(app)
    client.get("/itens/4/editar", headers={"referer": "http://testserver/equipas/2?aba=itens"})
    editado = client.post("/itens/4/editar", follow_redirects=False)
    eliminado = client.post(
        "/itens/4/eliminar",
        headers={"referer": "http://testserver/equipas/2?aba=itens"},
        follow_redirects=False,
    )

    assert editado.headers["location"] == "/equipas/2?aba=itens"
    assert eliminado.headers["location"] == "/equipas/2?aba=itens"


def test_validacao_e_autenticacao_mantem_destino_original():
    app = FastAPI()
    app.add_middleware(RetornoAposCriacaoMiddleware)
    app.add_middleware(SessionMiddleware, secret_key="teste")

    @app.post("/itens/novo")
    def validar_item():
        return RedirectResponse("/itens/novo", status_code=303)

    @app.post("/login-form")
    def iniciar_sessao():
        return RedirectResponse("/dashboard", status_code=303)

    @app.post("/acao-sem-permissao")
    def acao_sem_permissao():
        return RedirectResponse(
            "/dashboard",
            status_code=303,
            headers={"X-Context-Redirect-Locked": "1"},
        )

    client = TestClient(app)
    invalido = client.post(
        "/itens/novo",
        headers={"referer": "http://testserver/equipas/1"},
        follow_redirects=False,
    )
    login = client.post(
        "/login-form",
        headers={"referer": "http://testserver/login-form"},
        follow_redirects=False,
    )
    negado = client.post(
        "/acao-sem-permissao",
        headers={"referer": "http://testserver/equipas/1"},
        follow_redirects=False,
    )

    assert invalido.headers["location"] == "/itens/novo"
    assert login.headers["location"] == "/dashboard"
    assert negado.headers["location"] == "/dashboard"

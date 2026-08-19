from fastapi import FastAPI
from fastapi.responses import PlainTextResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

from middleware_retorno_criacao import (
    RetornoAposCriacaoMiddleware,
    _abre_dashboard_criado,
    _caminho_interno,
    _e_criacao,
)
from testsupport import TestClient


def test_retorno_so_aceita_caminhos_internos():
    assert _caminho_interno("https://exemplo.pt/equipas/3?aba=plantel") == "/equipas/3?aba=plantel"
    assert _caminho_interno("//externo.pt") is None
    assert _caminho_interno("https://externo.pt") is None
    assert _caminho_interno("/planeamento/equipas/1/anuais", "/planeamento/equipas/1/anuais") is None


def test_identifica_formularios_de_criacao_e_excecoes_de_ciclos():
    assert _e_criacao("/planeamento-clube/espacos/novo")
    assert _e_criacao("/planeamento-clube/espacos/1/disponibilidades")
    assert _e_criacao("/treino/planos/2/blocos")
    assert not _e_criacao("/planeamento/microciclos/2/editar")
    assert _abre_dashboard_criado("/planeamento/equipas/1/macrociclos/novo")
    assert _abre_dashboard_criado("/planeamento/macrociclos/2/mesociclos/novo")
    assert _abre_dashboard_criado("/planeamento/mesociclos/2/microciclos/novo")


def test_criacao_regressa_a_origem_mas_ciclos_abrem_o_dashboard():
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
    assert macro.headers["location"] == "/planeamento/macrociclos/8"

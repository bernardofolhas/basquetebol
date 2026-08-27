from types import SimpleNamespace

from starlette.datastructures import QueryParams

from services.pdf_filtros_service import (
    filtrar_itens_agenda,
    filtrar_jogos,
    obter_filtros_pdf,
)


def _request(query: str = ""):
    return SimpleNamespace(query_params=QueryParams(query))


def test_filtros_pdf_preservam_todo_o_conteudo_por_defeito():
    filtros = obter_filtros_pdf(_request())
    assert filtros["tipos"] == {"treino", "jogo", "atividade"}
    assert filtros["casa"] is True
    assert filtros["fora"] is True
    assert filtros["observacoes"] is True
    assert filtros["indicadores"] is True
    assert filtros["imagens"] is True


def test_calendario_permite_combinar_treinos_jogos_e_atividades():
    itens = [
        {"categoria": "treino", "titulo": "Treino"},
        {"categoria": "fisico", "titulo": "Treino fisico"},
        {"categoria": "jogo", "titulo": "Jogo"},
        {"categoria": "atividade_clube", "titulo": "Reuniao"},
    ]
    filtros = obter_filtros_pdf(_request("pdf_tipos=treino,atividade"))
    assert [item["titulo"] for item in filtrar_itens_agenda(itens, filtros)] == [
        "Treino", "Treino fisico", "Reuniao"
    ]


def test_jogos_permite_filtrar_casa_fora_e_competicao():
    jogos = [
        SimpleNamespace(em_casa=True, competicao="Campeonato Nacional"),
        SimpleNamespace(em_casa=False, competicao="Jogo amigavel"),
        SimpleNamespace(em_casa=True, competicao="Amigavel de preparacao"),
    ]
    filtros = obter_filtros_pdf(
        _request("pdf_casa=1&pdf_fora=0&pdf_competicao=amig%C3%A1veis")
    )
    assert filtrar_jogos(jogos, filtros) == [jogos[2]]


def test_opcoes_gerais_podem_ser_desativadas_individualmente():
    filtros = obter_filtros_pdf(
        _request("pdf_observacoes=0&pdf_indicadores=0&pdf_imagens=0")
    )
    assert filtros["observacoes"] is False
    assert filtros["indicadores"] is False
    assert filtros["imagens"] is False


def test_layout_global_inclui_configurador_de_pdf():
    from pathlib import Path

    raiz = Path(__file__).resolve().parents[2]
    base = (raiz / "frontend/templates/base.html").read_text(encoding="utf-8")
    modal = (raiz / "frontend/templates/partials/pdf_configurador.html").read_text(encoding="utf-8")
    script = (raiz / "frontend/static/js/pdf-configurador.js").read_text(encoding="utf-8")
    assert 'include "partials/pdf_configurador.html"' in base
    assert "pdf-configurador.js" in base
    assert "Conteúdo do calendário" in modal
    assert "Competição (opcional)" in modal
    assert 'a[href*="/pdf"]' in script

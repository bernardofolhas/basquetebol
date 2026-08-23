from types import SimpleNamespace

from services.conteudos_sessao_service import (
    CATEGORIAS_POR_CODIGO,
    atualizar_minutos_por_componente,
    categorias_conteudo_para_ui,
)


def test_conteudos_atualizam_totais_por_componente():
    sessao = SimpleNamespace(
        conteudos=[
            SimpleNamespace(categoria="tecnica_individual_ofensiva", minutos=20),
            SimpleNamespace(categoria="tecnica_individual_ofensiva", minutos=15),
            SimpleNamespace(categoria="capacidades_motoras", minutos=25),
            SimpleNamespace(categoria="psicologia", minutos=10),
        ],
    )
    atualizar_minutos_por_componente(sessao)

    assert sessao.min_tecnica_individual_ofensiva == 35
    assert sessao.min_fisicos == 25
    assert sessao.min_psicologicos == 10
    assert sessao.min_tatica_coletiva_defensiva == 0


def test_categorias_da_interface_correspondem_aos_totais_guardados():
    categorias = categorias_conteudo_para_ui()

    assert {categoria["codigo"] for categoria in categorias} == set(CATEGORIAS_POR_CODIGO)
    assert any(categoria["codigo"] == "psicologia" for categoria in categorias)

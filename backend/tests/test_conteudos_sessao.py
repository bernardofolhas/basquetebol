from datetime import date
from types import SimpleNamespace

from services.conteudos_sessao_service import (
    CATEGORIAS_POR_CODIGO,
    atualizar_minutos_por_componente,
    categorias_conteudo_para_ui,
    construir_visao_semanal_conteudos,
)
from services.volume_sessao_service import atualizar_volume_automatico
from routers.planeamento import _calcular_balanco_microciclo


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


def test_visao_semanal_organiza_conteudos_por_dia_e_categoria():
    sessao = SimpleNamespace(
        id=12,
        data=date(2026, 7, 22),
        numero_treino=3,
        conteudos=[SimpleNamespace(
            categoria="tatica_coletiva_ofensiva",
            descricao="Saída de pressão",
            minutos=18,
        )],
    )

    treinos = construir_visao_semanal_conteudos([sessao])

    assert len(treinos) == 1
    assert treinos[0]["dia_semana"] == "Quarta-feira"
    entrada = treinos[0]["conteudos_por_categoria"]["tatica_coletiva_ofensiva"][0]
    assert entrada == {
        "id": None,
        "descricao": "Saída de pressão",
        "minutos": 18,
    }


def test_graficos_do_microciclo_usam_o_nome_do_treino():
    campos_componentes = {
        "min_tecnica_individual_ofensiva": 0,
        "min_tecnica_individual_defensiva": 0,
        "min_tatica_individual_ofensiva": 0,
        "min_tatica_individual_defensiva": 0,
        "min_tatica_coletiva_ofensiva": 0,
        "min_tatica_coletiva_defensiva": 0,
        "min_fisicos": 0,
        "min_psicologicos": 0,
    }
    treino = SimpleNamespace(
        id=1, data=date(2026, 7, 22), hora_inicio="18:00", e_jogo=False,
        numero_treino=3, volume_minutos=90, intensidade_rpe=6,
        **campos_componentes,
    )
    jogo = SimpleNamespace(
        id=2, data=date(2026, 7, 23), hora_inicio="18:00", e_jogo=True,
        numero_treino=None, volume_minutos=None, intensidade_rpe=10,
        **campos_componentes,
    )

    _, dados_graficos = _calcular_balanco_microciclo([jogo, treino])

    assert dados_graficos == {
        "labels": ["Treino 3", "Jogo"],
        "volumes": [90, 0],
        "rpes": [6.0, 10.0],
    }


def test_jogo_assume_rpe_dez_automaticamente():
    jogo = SimpleNamespace(
        e_jogo=True,
        intensidade_rpe=None,
        volume_minutos=None,
        hora_inicio="18:00",
        hora_fim="19:30",
    )

    atualizar_volume_automatico(jogo)

    assert jogo.intensidade_rpe == 10


def test_visao_e_graficos_incluem_treinos_manuais_e_atribuidos():
    campos_componentes = {
        "min_tecnica_individual_ofensiva": 0,
        "min_tecnica_individual_defensiva": 0,
        "min_tatica_individual_ofensiva": 0,
        "min_tatica_individual_defensiva": 0,
        "min_tatica_coletiva_ofensiva": 0,
        "min_tatica_coletiva_defensiva": 0,
        "min_fisicos": 0,
        "min_psicologicos": 0,
    }
    treino_manual = SimpleNamespace(
        id=1, data=date(2026, 7, 21), hora_inicio=None, e_jogo=False,
        numero_treino=1, volume_minutos=75, intensidade_rpe=5, origem="manual",
        conteudos=[], **campos_componentes,
    )
    treino_atribuido = SimpleNamespace(
        id=2, data=date(2026, 7, 23), hora_inicio="19:00", e_jogo=False,
        numero_treino=1, volume_minutos=90, intensidade_rpe=7, origem="planeamento_global", tipo_treino="fisico",
        conteudos=[], **campos_componentes,
    )

    visao = construir_visao_semanal_conteudos([treino_atribuido, treino_manual])
    _, dados_graficos = _calcular_balanco_microciclo([treino_atribuido, treino_manual])

    assert [treino["sessao_id"] for treino in visao] == [1, 2]
    assert dados_graficos["labels"] == ["Treino 1", "Treino físico 1"]
    assert dados_graficos["volumes"] == [75, 90]
    assert dados_graficos["rpes"] == [5.0, 7.0]

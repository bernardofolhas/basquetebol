from datetime import date
from types import SimpleNamespace

from services.atribuicao_espaco_visual_service import construir_quadro_atribuicoes, cor_equipa


def test_quadro_tem_uma_linha_por_equipa_e_reservas_no_dia_certo():
    semanal = SimpleNamespace(data_inicio=date(2026, 9, 7), data_fim=date(2026, 9, 13))
    equipa_a = SimpleNamespace(id=14, nome="Sub-16 Femininos")
    equipa_b = SimpleNamespace(id=22, nome="Sub-18 Femininos")
    reserva = SimpleNamespace(
        equipa_id=22,
        data=date(2026, 9, 8),
        hora_inicio="18:30",
        hora_fim="20:00",
        espaco=SimpleNamespace(nome="Pavilhão Principal"),
    )

    quadro = construir_quadro_atribuicoes(semanal, [equipa_b, equipa_a], [reserva])

    assert [linha["equipa"].id for linha in quadro["linhas"]] == [14, 22]
    assert len(quadro["dias"]) == 7
    assert not quadro["linhas"][0]["celulas"][0]["reservas"]
    reservas_terca = quadro["linhas"][1]["celulas"][1]["reservas"]
    assert reservas_terca == [reserva]
    assert quadro["linhas"][1]["cor"] == cor_equipa(22)


def test_cor_da_equipa_e_estavel():
    assert cor_equipa(31) == cor_equipa(31)
    assert cor_equipa(None)["marca"] == "#475569"

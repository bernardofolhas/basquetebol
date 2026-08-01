from datetime import date, datetime

from formatacao import data_hora_pt, data_iso, data_pt, finalizar_valor_template


def test_data_pt_formata_objetos_e_strings_iso():
    assert data_pt(date(2026, 7, 31)) == "31/07/2026"
    assert data_pt("2026-07-31") == "31/07/2026"


def test_data_hora_pt_preserva_hora():
    assert data_hora_pt(datetime(2026, 7, 31, 19, 5)) == "31/07/2026 19:05"
    assert data_hora_pt("2026-07-31T19:05:42") == "31/07/2026 19:05"


def test_data_iso_mantem_formato_exigido_pelos_inputs_html():
    assert data_iso(date(2026, 7, 31)) == "2026-07-31"
    assert finalizar_valor_template(date(2026, 7, 31)) == "31/07/2026"

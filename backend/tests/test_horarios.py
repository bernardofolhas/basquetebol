from horarios import hora_eh_anterior, hora_valida, normalizar_hora


def test_normalizar_hora_preenche_zero_a_esquerda():
    assert normalizar_hora("9:05") == "09:05"


def test_normalizar_hora_rejeita_valor_invalido():
    assert normalizar_hora("25:00") is None


def test_hora_valida_aceita_vazio_quando_permitido():
    assert hora_valida("")


def test_hora_valida_exige_valor_quando_configurado():
    assert not hora_valida("", permitir_vazio=False)


def test_hora_eh_anterior_compara_horas_normalizadas():
    assert hora_eh_anterior("9:00", "10:00")
    assert not hora_eh_anterior("10:00", "09:59")

"""Mantém os horários dos exercícios alinhados com o início da sessão."""

from horarios import normalizar_hora


def _somar_minutos(hora: str | None, minutos: int | None) -> str | None:
    hora_normalizada = normalizar_hora(hora, permitir_vazio=False)
    if not hora_normalizada or minutos is None or minutos < 0:
        return hora_normalizada
    horas, minutos_hora = map(int, hora_normalizada.split(":"))
    total = (horas * 60 + minutos_hora + minutos) % (24 * 60)
    return f"{total // 60:02d}:{total % 60:02d}"


def recalcular_horas_exercicios(plano) -> str | None:
    """Recalcula todos os inícios pela ordem atual, sem alterar durações."""
    sessao = getattr(plano, "sessao", None)
    hora_corrente = normalizar_hora(
        getattr(sessao, "hora_inicio", None) or getattr(plano, "hora_inicio", None),
        permitir_vazio=False,
    )
    exercicios = list(getattr(plano, "exercicios", None) or [])
    if not hora_corrente:
        for exercicio in exercicios:
            exercicio.hora = None
        return None

    for exercicio in exercicios:
        exercicio.hora = hora_corrente
        hora_corrente = _somar_minutos(hora_corrente, exercicio.minutos)
    return hora_corrente

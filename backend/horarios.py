"""
Helpers pequenos e reutilizaveis para trabalhar com horas no formato HH:MM.
"""


def normalizar_hora(hora: str | None, *, permitir_vazio: bool = True) -> str | None:
    """
    Normaliza uma hora para HH:MM e devolve None quando estiver vazia.

    Aceita entradas como "9:00" ou "18h30" e converte-as para "09:00".
    """
    valor = (hora or "").strip()
    if not valor:
        return None if permitir_vazio else None

    valor = valor.casefold().replace("h", ":")
    partes = valor.split(":", 1)
    if len(partes) != 2 or not all(parte.isdigit() for parte in partes):
        return None

    horas, minutos = int(partes[0]), int(partes[1])
    if not (0 <= horas <= 23 and 0 <= minutos <= 59):
        return None

    return f"{horas:02d}:{minutos:02d}"


def hora_valida(hora: str | None, *, permitir_vazio: bool = True) -> bool:
    """Indica se a hora e valida para o formato esperado."""
    if not (hora or "").strip():
        return permitir_vazio
    return normalizar_hora(hora, permitir_vazio=False) is not None


def hora_eh_anterior(hora_inicio: str | None, hora_fim: str | None) -> bool:
    """Compara duas horas validas ja normalizadas para o mesmo dia."""
    hora_inicio_normalizada = normalizar_hora(hora_inicio, permitir_vazio=False)
    hora_fim_normalizada = normalizar_hora(hora_fim, permitir_vazio=False)
    if not hora_inicio_normalizada or not hora_fim_normalizada:
        return False
    return hora_inicio_normalizada < hora_fim_normalizada


def duracao_minutos(hora_inicio: str | None, hora_fim: str | None) -> int | None:
    """Calcula a duração entre duas horas válidas no mesmo dia.

    Devolve ``None`` quando o horário ainda está incompleto, para que o volume
    do treino se mantenha em branco até existir uma duração concreta.
    """
    inicio = normalizar_hora(hora_inicio, permitir_vazio=False)
    fim = normalizar_hora(hora_fim, permitir_vazio=False)
    if not inicio or not fim or inicio >= fim:
        return None
    inicio_minutos = int(inicio[:2]) * 60 + int(inicio[3:])
    fim_minutos = int(fim[:2]) * 60 + int(fim[3:])
    return fim_minutos - inicio_minutos

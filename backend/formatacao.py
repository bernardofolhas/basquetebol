from datetime import date, datetime
import re


_DATA_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_DATA_HORA_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})")


def data_pt(valor, vazio: str = "") -> str:
    """Formata datas para apresentação sem alterar o valor guardado."""
    if valor in (None, ""):
        return vazio
    if isinstance(valor, datetime):
        return valor.strftime("%d/%m/%Y")
    if isinstance(valor, date):
        return valor.strftime("%d/%m/%Y")
    correspondencia = _DATA_ISO.fullmatch(str(valor))
    if correspondencia:
        ano, mes, dia = correspondencia.groups()
        return f"{dia}/{mes}/{ano}"
    return str(valor)


def data_hora_pt(valor, vazio: str = "") -> str:
    if valor in (None, ""):
        return vazio
    if isinstance(valor, datetime):
        return valor.strftime("%d/%m/%Y %H:%M")
    if isinstance(valor, date):
        return valor.strftime("%d/%m/%Y")
    correspondencia = _DATA_HORA_ISO.match(str(valor))
    if correspondencia:
        ano, mes, dia, hora, minuto = correspondencia.groups()
        return f"{dia}/{mes}/{ano} {hora}:{minuto}"
    correspondencia = _DATA_ISO.fullmatch(str(valor))
    if correspondencia:
        ano, mes, dia = correspondencia.groups()
        return f"{dia}/{mes}/{ano}"
    return str(valor)


def data_iso(valor, vazio: str = "") -> str:
    """Mantém o formato técnico necessário a inputs HTML e URLs."""
    if valor in (None, ""):
        return vazio
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()[:10]
    return str(valor)


def finalizar_valor_template(valor):
    if isinstance(valor, datetime):
        return data_hora_pt(valor)
    if isinstance(valor, date):
        return data_pt(valor)
    return valor

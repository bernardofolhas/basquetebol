"""Normalização segura de desenhos táticos para o browser e para PDFs."""

import base64
import binascii
from io import BytesIO
import json
import re
from pathlib import Path

from PIL import Image, ImageOps


_DATA_URI_RE = re.compile(r"^data:(image/(?:png|jpeg|jpg|webp));base64,([A-Za-z0-9+/=\s]+)$", re.IGNORECASE)
_FORMATO_EDITAVEL = "desenho-tatico-v1"
_MAX_OBJECTOS = 500
_MAX_ESTADO_BYTES = 500_000


def normalizar_data_uri(valor: str | None) -> str | None:
    """Devolve um data URI raster válido, aceitando também Base64 legado."""
    if not valor or not isinstance(valor, str):
        return None
    valor = valor.strip()
    if valor.startswith("data:"):
        correspondencia = _DATA_URI_RE.fullmatch(valor)
        if not correspondencia:
            return None
        dados = "".join(correspondencia.group(2).split())
        try:
            base64.b64decode(dados, validate=True)
        except (ValueError, binascii.Error):
            return None
        mime = correspondencia.group(1).lower().replace("jpg", "jpeg")
        return f"data:{mime};base64,{dados}"

    try:
        dados = base64.b64decode("".join(valor.split()), validate=True)
    except (ValueError, binascii.Error):
        return None
    if not dados:
        return None
    return "data:image/png;base64," + base64.b64encode(dados).decode("ascii")


def decompor_desenho_editavel(valor: str | None) -> tuple[str | None, dict | None]:
    """Separa a imagem de apresentação do estado vetorial, aceitando PNGs antigos."""
    if not valor or not isinstance(valor, str):
        return None, None
    try:
        pacote = json.loads(valor)
    except (TypeError, json.JSONDecodeError):
        return valor, None
    if not isinstance(pacote, dict) or pacote.get("formato") != _FORMATO_EDITAVEL:
        return valor, None
    imagem = normalizar_data_uri(pacote.get("imagem"))
    estado = pacote.get("estado")
    if not imagem or not isinstance(estado, dict):
        return None, None
    return imagem, estado


def empacotar_desenho_editavel(imagem: str | None, estado: object) -> str | None:
    """Valida e guarda imagem e objetos editáveis na mesma coluna legada."""
    imagem_normalizada = normalizar_data_uri(imagem)
    if not imagem_normalizada or not isinstance(estado, dict):
        return None
    objectos = estado.get("objectos")
    if not isinstance(objectos, list) or len(objectos) > _MAX_OBJECTOS:
        return None
    estado_serializado = json.dumps(estado, ensure_ascii=False, separators=(",", ":"))
    if len(estado_serializado.encode("utf-8")) > _MAX_ESTADO_BYTES:
        return None
    return json.dumps(
        {"formato": _FORMATO_EDITAVEL, "imagem": imagem_normalizada, "estado": estado},
        ensure_ascii=False,
        separators=(",", ":"),
    )


def imagem_estatica_data_uri(caminho: Path, mime: str = "image/png") -> str | None:
    """Embebe uma imagem estática local para o renderer de PDF."""
    try:
        dados = caminho.read_bytes()
    except OSError:
        return None
    return f"data:{mime};base64," + base64.b64encode(dados).decode("ascii")


def compor_desenho_sobre_campo(caminho_campo: Path, desenho: str | None) -> str | None:
    """Cria a imagem final do PDF sem depender de sobreposições CSS."""
    desenho_normalizado = normalizar_data_uri(desenho)
    if not desenho_normalizado:
        return imagem_estatica_data_uri(caminho_campo)

    try:
        dados_desenho = base64.b64decode(desenho_normalizado.split(",", 1)[1])
        with Image.open(caminho_campo) as origem_campo, Image.open(BytesIO(dados_desenho)) as origem_desenho:
            campo = origem_campo.convert("RGBA")
            sobreposicao = ImageOps.contain(
                origem_desenho.convert("RGBA"),
                campo.size,
                method=Image.Resampling.LANCZOS,
            )
            posicao = (
                (campo.width - sobreposicao.width) // 2,
                (campo.height - sobreposicao.height) // 2,
            )
            campo.alpha_composite(sobreposicao, posicao)
            buffer = BytesIO()
            campo.save(buffer, format="PNG", optimize=True)
    except (OSError, ValueError, binascii.Error):
        return imagem_estatica_data_uri(caminho_campo)

    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")

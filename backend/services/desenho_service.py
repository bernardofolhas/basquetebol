"""Normalização segura de desenhos táticos para o browser e para PDFs."""

import base64
import binascii
from io import BytesIO
import re
from pathlib import Path

from PIL import Image, ImageOps


_DATA_URI_RE = re.compile(r"^data:(image/(?:png|jpeg|jpg|webp));base64,([A-Za-z0-9+/=\s]+)$", re.IGNORECASE)


def normalizar_data_uri(valor: str | None) -> str | None:
    """Devolve um data URI raster válido, aceitando também Base64 legado."""
    if not valor:
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

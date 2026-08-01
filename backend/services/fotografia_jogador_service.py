"""Validação e otimização segura das fotografias dos jogadores."""

from io import BytesIO
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError

from paths import JOGADORES_UPLOAD_DIR, STATIC_DIR


MAX_FOTOGRAFIA_BYTES = 5 * 1024 * 1024
MAX_FOTOGRAFIA_DIMENSION = 5000


def caminho_fotografia(url: str | None) -> Path | None:
    if not url or not url.startswith("/static/uploads/jogadores/"):
        return None
    nome = Path(url.rsplit("/", 1)[-1]).name
    pasta = JOGADORES_UPLOAD_DIR.resolve()
    caminho = (pasta / nome).resolve()
    return caminho if caminho.parent == pasta else None


def apagar_fotografia(url: str | None) -> None:
    caminho = caminho_fotografia(url)
    if caminho and caminho.is_file():
        caminho.unlink()


async def guardar_fotografia(ficheiro: UploadFile | None) -> str | None:
    if not ficheiro or not ficheiro.filename:
        return None
    if ficheiro.content_type not in {"image/png", "image/jpeg"}:
        raise ValueError("A fotografia deve estar em formato PNG ou JPEG.")
    dados = await ficheiro.read(MAX_FOTOGRAFIA_BYTES + 1)
    if len(dados) > MAX_FOTOGRAFIA_BYTES:
        raise ValueError("A fotografia não pode ultrapassar 5 MB.")
    try:
        imagem = Image.open(BytesIO(dados))
        imagem.verify()
        imagem = Image.open(BytesIO(dados))
    except (UnidentifiedImageError, OSError) as erro:
        raise ValueError("O ficheiro enviado não é uma imagem válida.") from erro
    if not imagem.width or not imagem.height or max(imagem.size) > MAX_FOTOGRAFIA_DIMENSION:
        raise ValueError("A fotografia deve ter dimensões válidas e no máximo 5000 px.")

    imagem = ImageOps.exif_transpose(imagem).convert("RGB")
    imagem.thumbnail((800, 800), Image.Resampling.LANCZOS)
    JOGADORES_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    destino = JOGADORES_UPLOAD_DIR / f"jogador-{uuid4().hex}.jpg"
    imagem.save(destino, format="JPEG", quality=86, optimize=True, progressive=True)
    return f"/static/uploads/jogadores/{destino.name}"

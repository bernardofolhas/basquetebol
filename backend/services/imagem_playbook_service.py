import base64
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError


MAX_IMAGEM_BYTES = 8 * 1024 * 1024
MAX_IMAGEM_PIXELS = 24_000_000
MAX_IMAGEM_DIMENSAO = (1800, 1400)
FORMATOS_ACEITES = {"JPEG", "PNG"}


def preparar_imagem_passo(conteudo: bytes) -> str:
    """Valida e otimiza uma imagem para armazenamento seguro no passo."""
    if not conteudo:
        raise ValueError("Seleciona uma imagem PNG ou JPEG.")
    if len(conteudo) > MAX_IMAGEM_BYTES:
        raise ValueError("A imagem não pode ultrapassar 8 MB.")

    try:
        imagem = Image.open(BytesIO(conteudo))
        imagem.verify()
        imagem = Image.open(BytesIO(conteudo))
    except (UnidentifiedImageError, OSError, ValueError) as erro:
        raise ValueError("O ficheiro não é uma imagem PNG ou JPEG válida.") from erro

    if imagem.format not in FORMATOS_ACEITES:
        raise ValueError("Apenas são aceites imagens PNG e JPEG.")
    if imagem.width * imagem.height > MAX_IMAGEM_PIXELS:
        raise ValueError("A imagem tem dimensões demasiado grandes.")

    imagem = ImageOps.exif_transpose(imagem)
    imagem.thumbnail(MAX_IMAGEM_DIMENSAO, Image.Resampling.LANCZOS)

    saida = BytesIO()
    tem_transparencia = imagem.mode in ("RGBA", "LA") or (
        imagem.mode == "P" and "transparency" in imagem.info
    )
    if tem_transparencia:
        imagem.convert("RGBA").save(saida, format="PNG", optimize=True)
        mime = "image/png"
    else:
        imagem.convert("RGB").save(
            saida,
            format="JPEG",
            quality=88,
            optimize=True,
            progressive=True,
        )
        mime = "image/jpeg"

    codificada = base64.b64encode(saida.getvalue()).decode("ascii")
    return f"data:{mime};base64,{codificada}"

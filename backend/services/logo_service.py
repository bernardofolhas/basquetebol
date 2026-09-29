"""Validação e normalização de logótipos com fundo transparente."""

from collections import deque
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError

from paths import BRANDING_DIR, JOGADORES_UPLOAD_DIR, STATIC_DIR


MAX_LOGO_BYTES = 2 * 1024 * 1024
MAX_LOGO_DIMENSION = 4000


def remover_fundo_ligado_as_margens(imagem: Image.Image, tolerancia: int = 48) -> Image.Image:
    """Remove apenas o fundo semelhante aos cantos e ligado às margens."""
    resultado = ImageOps.exif_transpose(imagem).convert("RGBA")
    largura, altura = resultado.size
    pixels = resultado.load()
    cantos = [
        pixels[0, 0],
        pixels[largura - 1, 0],
        pixels[0, altura - 1],
        pixels[largura - 1, altura - 1],
    ]
    opacos = [cor for cor in cantos if cor[3] > 16]
    if opacos:
        dominante = max(
            opacos,
            key=lambda cor: (
                sum(max(abs(cor[indice] - outra[indice]) for indice in range(3)) <= 32 for outra in opacos),
                sum(cor[:3]),
            ),
        )
        referencias = [
            cor for cor in opacos
            if max(abs(cor[indice] - dominante[indice]) for indice in range(3)) <= 32
        ]
    else:
        referencias = []

    def pertence_ao_fundo(x: int, y: int) -> bool:
        cor = pixels[x, y]
        if cor[3] <= 16:
            return True
        return bool(referencias) and any(
            referencia[3] > 16
            and max(abs(cor[indice] - referencia[indice]) for indice in range(3)) <= tolerancia
            for referencia in referencias
        )

    fila = deque()
    visitados = bytearray(largura * altura)

    def enfileirar(x: int, y: int) -> None:
        indice = y * largura + x
        if not visitados[indice]:
            visitados[indice] = 1
            fila.append((x, y))

    for x in range(largura):
        enfileirar(x, 0)
        enfileirar(x, altura - 1)
    for y in range(altura):
        enfileirar(0, y)
        enfileirar(largura - 1, y)

    while fila:
        x, y = fila.popleft()
        if not pertence_ao_fundo(x, y):
            continue
        vermelho, verde, azul, _ = pixels[x, y]
        pixels[x, y] = (vermelho, verde, azul, 0)
        if x:
            enfileirar(x - 1, y)
        if x + 1 < largura:
            enfileirar(x + 1, y)
        if y:
            enfileirar(x, y - 1)
        if y + 1 < altura:
            enfileirar(x, y + 1)
    return resultado


def caminho_logo_guardado(url: str | None) -> Path | None:
    if not url:
        return None
    opcoes = (
        ("/static/uploads/branding/", BRANDING_DIR),
        # Compatibilidade com símbolos de adversários guardados como fotografia.
        ("/static/uploads/jogadores/", JOGADORES_UPLOAD_DIR),
    )
    for prefixo, pasta_base in opcoes:
        if not url.startswith(prefixo):
            continue
        nome = Path(url.rsplit("/", 1)[-1]).name
        pasta = pasta_base.resolve()
        caminho = (pasta / nome).resolve()
        return caminho if caminho.parent == pasta else None
    return None


def apagar_logo_guardado(url: str | None) -> None:
    caminho = caminho_logo_guardado(url)
    if caminho and caminho.is_file():
        caminho.unlink()


async def guardar_logo_transparente(ficheiro: UploadFile | None, nome: str) -> str | None:
    if not ficheiro or not ficheiro.filename:
        return None
    if ficheiro.content_type not in {"image/png", "image/jpeg"}:
        raise ValueError("O logótipo deve estar em formato PNG ou JPEG.")
    dados = await ficheiro.read(MAX_LOGO_BYTES + 1)
    if len(dados) > MAX_LOGO_BYTES:
        raise ValueError("O logótipo não pode ultrapassar 2 MB.")
    try:
        imagem = Image.open(BytesIO(dados))
        imagem.verify()
        imagem = Image.open(BytesIO(dados))
    except (UnidentifiedImageError, OSError) as erro:
        raise ValueError("O ficheiro enviado não é uma imagem válida.") from erro
    if not imagem.width or not imagem.height or max(imagem.size) > MAX_LOGO_DIMENSION:
        raise ValueError("O logótipo deve ter dimensões válidas e no máximo 4000 px.")

    imagem.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
    imagem = remover_fundo_ligado_as_margens(imagem)
    BRANDING_DIR.mkdir(parents=True, exist_ok=True)
    destino = BRANDING_DIR / f"{nome}-{uuid4().hex[:12]}.png"
    imagem.save(destino, format="PNG", optimize=True)
    return f"/static/uploads/branding/{destino.name}"

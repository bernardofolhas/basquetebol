import base64
from io import BytesIO

from PIL import Image, ImageDraw

from services.desenho_service import (
    compor_desenho_sobre_campo,
    imagem_estatica_data_uri,
    normalizar_data_uri,
)


def test_normaliza_base64_legado_para_data_uri_png():
    valor = base64.b64encode(b"desenho").decode("ascii")
    resultado = normalizar_data_uri(valor)
    assert resultado == f"data:image/png;base64,{valor}"


def test_preserva_data_uri_raster_valido_e_rejeita_svg():
    valor = base64.b64encode(b"desenho").decode("ascii")
    assert normalizar_data_uri(f"data:image/png;base64,{valor}")
    assert normalizar_data_uri("data:image/svg+xml;base64,abc") is None


def test_embebe_imagem_estatica(tmp_path):
    imagem = tmp_path / "campo.png"
    imagem.write_bytes(b"campo")
    assert imagem_estatica_data_uri(imagem) == "data:image/png;base64," + base64.b64encode(b"campo").decode("ascii")


def test_compoe_desenho_transparente_sobre_campo(tmp_path):
    caminho_campo = tmp_path / "campo.png"
    Image.new("RGBA", (100, 100), "white").save(caminho_campo)
    desenho = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    ImageDraw.Draw(desenho).rectangle((40, 40, 60, 60), fill="red")
    buffer = BytesIO()
    desenho.save(buffer, format="PNG")
    data_uri = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")

    resultado = compor_desenho_sobre_campo(caminho_campo, data_uri)
    imagem_final = Image.open(BytesIO(base64.b64decode(resultado.split(",", 1)[1]))).convert("RGBA")

    assert imagem_final.getpixel((50, 50))[:3] == (255, 0, 0)
    assert imagem_final.getpixel((5, 5))[:3] == (255, 255, 255)

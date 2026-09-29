from pathlib import Path

from PIL import Image, ImageDraw

from services.logo_service import remover_fundo_ligado_as_margens


ROOT = Path(__file__).resolve().parents[2]


def test_remove_fundo_exterior_sem_apagar_branco_interior_do_emblema():
    imagem = Image.new("RGB", (9, 9), "white")
    desenho = ImageDraw.Draw(imagem)
    desenho.rectangle((2, 2, 6, 6), outline="black", width=1)

    resultado = remover_fundo_ligado_as_margens(imagem)

    assert resultado.getpixel((0, 0))[3] == 0
    assert resultado.getpixel((2, 2))[3] == 255
    assert resultado.getpixel((4, 4)) == (255, 255, 255, 255)


def test_apresentacao_dos_logotipos_nao_forca_caixas_brancas():
    estilos = {
        "design": (ROOT / "frontend" / "static" / "css" / "design-system.css").read_text(encoding="utf-8"),
        "sidebar": (ROOT / "frontend" / "static" / "css" / "sidebar.css").read_text(encoding="utf-8"),
        "scouting": (ROOT / "frontend" / "static" / "css" / "scouting-department.css").read_text(encoding="utf-8"),
        "pdf": (ROOT / "frontend" / "templates" / "partials" / "pdf_branding.html").read_text(encoding="utf-8"),
        "relatorio": (ROOT / "frontend" / "templates" / "relatorios" / "_scouting_estilos.html").read_text(encoding="utf-8"),
        "poster": (ROOT / "frontend" / "templates" / "relatorios" / "_poster.html").read_text(encoding="utf-8"),
    }

    assert "background: transparent" in estilos["design"]
    assert "background:transparent" in estilos["sidebar"]
    assert ".scouting-opponent-brand img" in estilos["scouting"]
    assert "background: transparent" in estilos["pdf"]
    assert "background:transparent" in estilos["relatorio"]
    assert ".poster-logo{border-radius:0!important;background:transparent!important" in estilos["poster"]


def test_simbolo_adversario_usa_pipeline_de_logotipo():
    rota = (ROOT / "backend" / "routers" / "scouting.py").read_text(encoding="utf-8")
    lista = (ROOT / "frontend" / "templates" / "scouting" / "index.html").read_text(encoding="utf-8")

    assert "guardar_logo_transparente(" in rota
    assert "apagar_logo_guardado(anterior)" in rota
    assert "item.simbolo" in lista
    assert "scouting-opponent-mark{% if item.simbolo %} has-image" in lista

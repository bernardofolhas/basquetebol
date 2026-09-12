from io import BytesIO
from zipfile import ZipFile

from pypdf import PdfReader, PdfWriter

from routers.exportacoes import _arquivar_pdfs, _juntar_pdfs


def _pdf_vazio(paginas: int) -> bytes:
    escritor = PdfWriter()
    for _ in range(paginas):
        escritor.add_blank_page(width=100, height=100)
    destino = BytesIO()
    escritor.write(destino)
    return destino.getvalue()


def test_exportacao_multipla_junta_todas_as_paginas_pela_ordem_selecionada():
    resultado = _juntar_pdfs([
        ("Macrociclo 1", _pdf_vazio(2)),
        ("Treino 1", _pdf_vazio(1)),
    ])

    assert len(PdfReader(BytesIO(resultado)).pages) == 3


def test_exportacao_multipla_cria_zip_com_documentos_separados_e_numerados():
    resultado = _arquivar_pdfs([
        ("Macrociclo 1", _pdf_vazio(1)),
        ("Treino físico 1", _pdf_vazio(1)),
    ])

    with ZipFile(BytesIO(resultado)) as arquivo:
        assert arquivo.namelist() == ["01_Macrociclo_1.pdf", "02_Treino_fisico_1.pdf"]
        assert all(PdfReader(BytesIO(arquivo.read(nome))).pages for nome in arquivo.namelist())

"""Helpers comuns para exportações PDF com a identidade do clube."""

import base64
import binascii
from datetime import date
from io import BytesIO
import re
import unicodedata
from urllib.parse import quote

from PIL import Image, UnidentifiedImageError
import weasyprint
from template_config import Jinja2Templates

from paths import STATIC_DIR, TEMPLATES_DIR
from services.desenho_service import imagem_estatica_data_uri
from services.identidade_clube_service import CORES_PADRAO, caminho_ficheiro_logo
from services.logo_service import remover_fundo_ligado_as_margens
from services.pdf_filtros_service import obter_filtros_pdf


templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def content_disposition_pdf(nome: str) -> str:
    """Cria um nome de download legivel, seguro e compativel com acentos."""
    nome_limpo = re.sub(r'[\r\n"\\/]+', " ", (nome or "Documento").strip())
    nome_limpo = re.sub(r"\s+", " ", nome_limpo)
    if not nome_limpo.lower().endswith(".pdf"):
        nome_limpo += ".pdf"

    nome_ascii = (
        unicodedata.normalize("NFKD", nome_limpo)
        .encode("ascii", "ignore")
        .decode("ascii")
    ) or "Documento.pdf"
    return f"attachment; filename=\"{nome_ascii}\"; filename*=UTF-8''{quote(nome_limpo)}"


def nome_curto_pessoa(nome: str | None) -> str:
    """Mantém os rodapés legíveis com o primeiro e último nome."""
    partes = (nome or "").split()
    if len(partes) <= 2:
        return " ".join(partes)
    return f"{partes[0]} {partes[-1]}"


def simbolo_cabecalho_sem_fundo(uri: str | None) -> str | None:
    """Deixa visível a cor do cabeçalho através de fundos opacos uniformes."""
    if not uri or not uri.startswith("data:image/") or ";base64," not in uri:
        return uri
    try:
        imagem = Image.open(BytesIO(base64.b64decode(uri.split(",", 1)[1])))
        imagem.thumbnail((500, 500), Image.Resampling.LANCZOS)
        imagem = imagem.convert("RGBA")
        largura, altura = imagem.size
        cantos = [imagem.getpixel(ponto) for ponto in ((0, 0), (largura - 1, 0), (0, altura - 1), (largura - 1, altura - 1))]
        referencia = cantos[0]
        if referencia[3] < 250 or sum(
            cor[3] >= 250 and max(abs(cor[i] - referencia[i]) for i in range(3)) <= 24
            for cor in cantos
        ) < 3:
            return uri
        imagem = remover_fundo_ligado_as_margens(imagem)
        saida = BytesIO()
        imagem.save(saida, format="PNG")
        return "data:image/png;base64," + base64.b64encode(saida.getvalue()).decode("ascii")
    except (OSError, ValueError, UnidentifiedImageError, binascii.Error):
        return uri


def _identidade_para_pdf(identidade: dict, *, scouting: bool = False) -> dict:
    """Embebe logos locais para que o WeasyPrint não dependa de HTTP."""
    resultado = dict(identidade)
    for campo in ("logo_principal", "logo_secundario"):
        caminho = caminho_ficheiro_logo(STATIC_DIR, resultado.get(campo))
        if not caminho or not caminho.is_file():
            resultado[campo] = None
            continue
        mime = "image/jpeg" if caminho.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
        uri = imagem_estatica_data_uri(caminho, mime)
        resultado[campo] = simbolo_cabecalho_sem_fundo(uri) if scouting and campo == "logo_principal" else uri
    return resultado


def preparar_contexto_pdf(request, contexto: dict | None = None, identidade: dict | None = None) -> dict:
    """Adiciona marca, pedido e data de exportação a qualquer template PDF."""
    resultado = dict(contexto or {})
    identidade_pedido = getattr(getattr(request, "state", None), "identidade_clube", None)
    identidade_origem = resultado.get("identidade") or identidade or identidade_pedido or dict(CORES_PADRAO)
    scouting = resultado.get("tipo_relatorio") in {"scouting-individual", "scouting-coletivo"}
    cabecalho_com_simbolos = scouting or (
        resultado.get("formato") == "facil" and resultado.get("tipo_relatorio") in {"roster", "plano-jogo"}
    )
    resultado["identidade"] = _identidade_para_pdf(identidade_origem, scouting=cabecalho_com_simbolos)
    if cabecalho_com_simbolos and resultado.get("simbolo_adversario"):
        resultado["simbolo_adversario"] = simbolo_cabecalho_sem_fundo(resultado["simbolo_adversario"])
    resultado.setdefault("hoje", date.today())
    resultado.setdefault("data_exportacao", date.today())
    if "nome_treinador" in resultado:
        resultado["nome_treinador"] = nome_curto_pessoa(resultado["nome_treinador"])
    resultado["pdf_filtros"] = obter_filtros_pdf(request)
    resultado["request"] = request
    return resultado


def renderizar_pdf(request, template_nome: str, contexto: dict | None = None) -> bytes:
    """Renderiza HTML independente do layout da aplicação para PDF."""
    html = templates.get_template(template_nome).render(preparar_contexto_pdf(request, contexto))
    return weasyprint.HTML(string=html, base_url=str(request.base_url)).write_pdf()

"""Helpers comuns para exportações PDF com a identidade do clube."""

from datetime import date
import re
import unicodedata
from urllib.parse import quote

import weasyprint
from template_config import Jinja2Templates

from paths import STATIC_DIR, TEMPLATES_DIR
from services.desenho_service import imagem_estatica_data_uri
from services.identidade_clube_service import CORES_PADRAO, caminho_ficheiro_logo


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


def _identidade_para_pdf(identidade: dict) -> dict:
    """Embebe logos locais para que o WeasyPrint não dependa de HTTP."""
    resultado = dict(identidade)
    for campo in ("logo_principal", "logo_secundario"):
        caminho = caminho_ficheiro_logo(STATIC_DIR, resultado.get(campo))
        if not caminho or not caminho.is_file():
            resultado[campo] = None
            continue
        mime = "image/jpeg" if caminho.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
        resultado[campo] = imagem_estatica_data_uri(caminho, mime)
    return resultado


def preparar_contexto_pdf(request, contexto: dict | None = None, identidade: dict | None = None) -> dict:
    """Adiciona marca, pedido e data de exportação a qualquer template PDF."""
    resultado = dict(contexto or {})
    identidade_pedido = getattr(getattr(request, "state", None), "identidade_clube", None)
    identidade_origem = resultado.get("identidade") or identidade or identidade_pedido or dict(CORES_PADRAO)
    resultado["identidade"] = _identidade_para_pdf(identidade_origem)
    resultado.setdefault("hoje", date.today())
    resultado.setdefault("data_exportacao", date.today())
    if "nome_treinador" in resultado:
        resultado["nome_treinador"] = nome_curto_pessoa(resultado["nome_treinador"])
    resultado["request"] = request
    return resultado


def renderizar_pdf(request, template_nome: str, contexto: dict | None = None) -> bytes:
    """Renderiza HTML independente do layout da aplicação para PDF."""
    html = templates.get_template(template_nome).render(preparar_contexto_pdf(request, contexto))
    return weasyprint.HTML(string=html, base_url=str(request.base_url)).write_pdf()

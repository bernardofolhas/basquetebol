from datetime import datetime
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from template_config import Jinja2Templates
from sqlalchemy.orm import Session

from auth_deps import exigir_superadmin
from database import get_db
from flash import set_flash
from paths import TEMPLATES_DIR
from services.identidade_clube_service import (
    CORES_PADRAO,
    garantir_identidade_clube,
    identidade_para_contexto,
    normalizar_cor,
)
from services.logo_service import apagar_logo_guardado, guardar_logo_transparente


router = APIRouter(prefix="/administracao/identidade")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _validar_cor(valor: str, nome: str, fallback: str) -> str:
    normalizada = normalizar_cor(valor, "")
    if not normalizada:
        raise ValueError(f"A {nome} deve estar no formato #RRGGBB.")
    return normalizada


def _apagar_logo(url: str | None) -> None:
    apagar_logo_guardado(url)


async def _guardar_logo(ficheiro: UploadFile | None, nome: str) -> str | None:
    return await guardar_logo_transparente(ficheiro, nome)


@router.get("", response_class=HTMLResponse)
def pagina_identidade(
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_superadmin),
):
    identidade = garantir_identidade_clube(db)
    return templates.TemplateResponse(request, "administracao/identidade.html", {
        "utilizador": utilizador,
        "identidade": identidade,
        "identidade_ui": identidade_para_contexto(identidade),
    })


@router.post("")
async def guardar_identidade(
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_superadmin),
    nome_oficial: str = Form(...),
    nome_curto: str = Form(""),
    cor_principal: str = Form("#f97316"),
    cor_secundaria: str = Form("#1f2937"),
    cor_destaque: str = Form("#0ea5e9"),
    texto_rodape: str = Form(""),
    epoca_predefinida: str = Form(""),
    logo_principal: UploadFile | None = File(None),
    logo_secundario: UploadFile | None = File(None),
    remover_logo_principal: str = Form("false"),
    remover_logo_secundario: str = Form("false"),
):
    identidade = garantir_identidade_clube(db)
    try:
        identidade.nome_oficial = nome_oficial.strip() or CORES_PADRAO["nome_oficial"]
        identidade.nome_curto = nome_curto.strip() or None
        identidade.cor_principal = _validar_cor(cor_principal, "cor principal", CORES_PADRAO["cor_principal"])
        identidade.cor_secundaria = _validar_cor(cor_secundaria, "cor secundária", CORES_PADRAO["cor_secundaria"])
        identidade.cor_destaque = _validar_cor(cor_destaque, "cor de destaque", CORES_PADRAO["cor_destaque"])
        identidade.texto_rodape = texto_rodape.strip() or None
        identidade.epoca_predefinida = epoca_predefinida.strip() or None

        if remover_logo_principal == "true":
            _apagar_logo(identidade.logo_principal)
            identidade.logo_principal = None
        if remover_logo_secundario == "true":
            _apagar_logo(identidade.logo_secundario)
            identidade.logo_secundario = None
        prefixo = f"clube-{identidade.clube_id}"
        novo_principal = await _guardar_logo(logo_principal, f"{prefixo}-logo-principal")
        novo_secundario = await _guardar_logo(logo_secundario, f"{prefixo}-logo-secundario")
        if novo_principal:
            _apagar_logo(identidade.logo_principal)
            identidade.logo_principal = novo_principal
        if novo_secundario:
            _apagar_logo(identidade.logo_secundario)
            identidade.logo_secundario = novo_secundario
        identidade.atualizado_em = datetime.now()
        from services.auditoria_service import registar_auditoria
        registar_auditoria(db, utilizador, "alterar_identidade", "clube", identidade.clube_id, request=request)
        db.commit()
    except ValueError as erro:
        db.rollback()
        set_flash(request, str(erro), "error")
        return RedirectResponse(url="/administracao/identidade", status_code=303)

    set_flash(request, "Identidade do clube atualizada.")
    return RedirectResponse(url="/administracao/identidade", status_code=303)

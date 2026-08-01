from datetime import date as dt

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from template_config import Jinja2Templates
from sqlalchemy.orm import Session

from auth_deps import exigir_autenticacao, exigir_coordenacao
from database import get_db
from flash import set_flash
from models.atividade import Atividade
from paths import TEMPLATES_DIR

router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("/atividades", response_class=HTMLResponse)
def listar_atividades(
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    """Lista as atividades globais da aplicação."""
    atividades = db.query(Atividade).order_by(Atividade.data).all()
    return templates.TemplateResponse(request, "atividades.html", {
        "utilizador": utilizador,
        "atividades": atividades,
    })


@router.post("/atividades/nova")
async def criar_atividade(
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_coordenacao),
    titulo: str = Form(...),
    data: str = Form(...),
    local: str = Form(""),
    tipo: str = Form(""),
    descricao: str = Form(""),
    observacoes: str = Form(""),
):
    """Cria uma nova atividade global."""
    atividade = Atividade(
        titulo=titulo,
        data=dt.fromisoformat(data),
        local=local or None,
        tipo=tipo or None,
        descricao=descricao or None,
        observacoes=observacoes or None,
    )
    db.add(atividade)
    db.commit()
    set_flash(request, f"Atividade '{titulo}' criada com sucesso.")
    return RedirectResponse(url="/atividades", status_code=303)

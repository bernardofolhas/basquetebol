import json
import re

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from template_config import Jinja2Templates
from sqlalchemy.orm import Session

from auth_deps import exigir_autenticacao, exigir_coordenacao
from database import get_db
from paths import TEMPLATES_DIR
from services.dashboard_service import (
    get_dashboard_admin,
    get_dashboard_clube,
    get_dashboard_clube_carga,
    get_dashboard_clube_espacos,
    get_dashboard_clube_executado,
    get_dashboard_clube_sincronizacao,
    get_dashboard_coordenador,
    get_dashboard_fisioterapeuta,
    get_dashboard_treinador,
)

router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

CHAVE_DASHBOARD_RE = re.compile(r"^[a-z0-9:_-]{1,80}$")
CHAVE_WIDGET_RE = re.compile(r"^[a-z0-9:_-]{1,100}$")


@router.post("/dashboard/preferencias")
async def guardar_preferencias_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    """Guarda os blocos ocultos de um dashboard para o utilizador autenticado."""
    try:
        dados = await request.json()
    except (ValueError, json.JSONDecodeError):
        return JSONResponse({"sucesso": False, "erro": "Configuração inválida."}, status_code=400)

    chave = str(dados.get("dashboard") or "").strip().lower()
    ocultos_recebidos = dados.get("ocultos", [])
    if not CHAVE_DASHBOARD_RE.fullmatch(chave) or not isinstance(ocultos_recebidos, list):
        return JSONResponse({"sucesso": False, "erro": "Configuração inválida."}, status_code=422)

    ocultos = []
    for valor in ocultos_recebidos[:100]:
        widget = str(valor or "").strip().lower()
        if CHAVE_WIDGET_RE.fullmatch(widget) and widget not in ocultos:
            ocultos.append(widget)

    try:
        preferencias = json.loads(utilizador.preferencias_dashboard or "{}")
    except (TypeError, ValueError):
        preferencias = {}
    if not isinstance(preferencias, dict):
        preferencias = {}

    if ocultos:
        preferencias[chave] = ocultos
    else:
        preferencias.pop(chave, None)
    utilizador.preferencias_dashboard = json.dumps(
        preferencias,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    db.commit()
    return JSONResponse({"sucesso": True, "dashboard": chave, "ocultos": ocultos})


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request,
    equipa_id: int | None = None,
    dias: int = 7,
    metrica: str = "rpe",
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    """Renderiza o dashboard adequado ao perfil do utilizador autenticado."""
    if utilizador.perfil.value == "superadministrador" and not getattr(request.state, "clube_atual", None):
        return RedirectResponse(url="/superadmin/clubes", status_code=303)
    if utilizador.perfil.value == "atleta":
        return RedirectResponse(url="/questionarios/disponiveis", status_code=303)
    if utilizador.perfil.value == "fisioterapeuta":
        contexto = get_dashboard_fisioterapeuta(
            db,
            utilizador,
            equipa_id=equipa_id,
            dias=dias,
            metrica=metrica,
        )
        return templates.TemplateResponse(request, "dashboard_fisioterapeuta.html", contexto)
    if utilizador.perfil.value in {"treinador", "staff"}:
        contexto = get_dashboard_treinador(db, utilizador)
        return templates.TemplateResponse(request, "dashboard_treinador.html", contexto)

    if utilizador.perfil.value == "secretaria":
        return RedirectResponse(url="/secretaria/pendencias", status_code=303)

    if utilizador.perfil.value == "coordenador":
        contexto = get_dashboard_coordenador(db, utilizador)
        return templates.TemplateResponse(request, "dashboard_coordenador.html", contexto)

    contexto = get_dashboard_admin(db, utilizador)
    return templates.TemplateResponse(request, "dashboard_admin.html", contexto)


@router.get("/dashboard/clube", response_class=HTMLResponse)
def dashboard_clube(
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_coordenacao),
):
    """Mostra o dashboard operacional geral do clube."""
    contexto = get_dashboard_clube(db, utilizador)
    return templates.TemplateResponse(request, "dashboard_clube.html", contexto)


@router.get("/dashboard/clube/espacos", response_class=HTMLResponse)
def dashboard_clube_espacos(
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_coordenacao),
):
    """Mostra o dashboard operacional de ocupação de espaços."""
    contexto = get_dashboard_clube_espacos(db, utilizador)
    return templates.TemplateResponse(request, "dashboard_clube_espacos.html", contexto)


@router.get("/dashboard/clube/carga", response_class=HTMLResponse)
def dashboard_clube_carga(
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_coordenacao),
):
    """Mostra o dashboard operacional de carga de treino."""
    contexto = get_dashboard_clube_carga(db, utilizador)
    return templates.TemplateResponse(request, "dashboard_clube_carga.html", contexto)


@router.get("/dashboard/clube/executado", response_class=HTMLResponse)
def dashboard_clube_executado(
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_coordenacao),
):
    """Mostra o dashboard de sessões planeadas, ativas e desativadas."""
    contexto = get_dashboard_clube_executado(db, utilizador)
    return templates.TemplateResponse(request, "dashboard_clube_executado.html", contexto)


@router.get("/dashboard/clube/sincronizacao", response_class=HTMLResponse)
def dashboard_clube_sincronizacao(
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_coordenacao),
):
    """Mostra o dashboard operacional do estado de sincronização."""
    contexto = get_dashboard_clube_sincronizacao(db, utilizador)
    return templates.TemplateResponse(request, "dashboard_clube_sincronizacao.html", contexto)

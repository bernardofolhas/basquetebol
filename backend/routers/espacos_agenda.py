from datetime import date as date_type, timedelta

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from template_config import Jinja2Templates
from sqlalchemy.orm import Session, joinedload

from auth_deps import exigir_autenticacao, exigir_coordenacao
from database import get_db
from flash import set_flash
from horarios import hora_eh_anterior, hora_valida, normalizar_hora
from models.equipa import Equipa
from models.espaco_agenda import AgendaEspacoEquipa
from models.espaco_treino import EspacoTreino
from paths import TEMPLATES_DIR

router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# ─────────────────────────────────────────
# LISTA / GESTÃO DE DISTRIBUIÇÃO
# URL: GET /espacos/agenda
# ─────────────────────────────────────────
@router.get("/espacos/agenda", response_class=HTMLResponse)
def agenda_espacos(
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_coordenacao),
    equipa_id: int = Query(0),
    semana: str = Query(""),
):
    equipas = db.query(Equipa).order_by(Equipa.nome).all()
    espacos = db.query(EspacoTreino).filter(EspacoTreino.ativo == True).order_by(EspacoTreino.nome).all()

    query = (
        db.query(AgendaEspacoEquipa)
        .options(joinedload(AgendaEspacoEquipa.espaco), joinedload(AgendaEspacoEquipa.equipa))
        .filter(AgendaEspacoEquipa.ativo == True)
        .order_by(AgendaEspacoEquipa.data, AgendaEspacoEquipa.hora_inicio)
    )
    if equipa_id:
        query = query.filter(AgendaEspacoEquipa.equipa_id == equipa_id)
    if semana:
        try:
            data_semana = date_type.fromisoformat(semana)
            segunda = data_semana - timedelta(days=data_semana.weekday())
            domingo = segunda + timedelta(days=6)
            query = query.filter(
                AgendaEspacoEquipa.data >= segunda,
                AgendaEspacoEquipa.data <= domingo,
            )
        except ValueError:
            semana = ""

    atribuicoes = query.all()

    return templates.TemplateResponse(request, "espacos/agenda.html", {
        "utilizador": utilizador,
        "equipas": equipas,
        "espacos": espacos,
        "atribuicoes": atribuicoes,
        "equipa_id_filtro": equipa_id,
        "semana_filtro": semana,
        "hoje": date_type.today().isoformat(),
    })


# ─────────────────────────────────────────
# CRIAR ATRIBUIÇÃO
# URL: POST /espacos/agenda/nova
# ─────────────────────────────────────────
@router.post("/espacos/agenda/nova")
async def criar_atribuicao_espaco(
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_coordenacao),
    espaco_id: int = Form(...),
    equipa_id: int = Form(...),
    data: str = Form(...),
    hora_inicio: str = Form(...),
    hora_fim: str = Form(...),
    observacoes: str = Form(""),
):
    erros = []
    if not hora_valida(hora_inicio, permitir_vazio=False):
        erros.append("Hora de início inválida.")
    if not hora_valida(hora_fim, permitir_vazio=False):
        erros.append("Hora de término inválida.")
    hora_inicio = normalizar_hora(hora_inicio, permitir_vazio=False)
    hora_fim = normalizar_hora(hora_fim, permitir_vazio=False)
    if hora_inicio and hora_fim and not hora_eh_anterior(hora_inicio, hora_fim):
        erros.append("A hora de início deve ser anterior à de término.")
    try:
        data_obj = date_type.fromisoformat(data)
    except ValueError:
        erros.append("Data inválida.")
        data_obj = None

    if erros:
        set_flash(request, " ".join(erros), "error")
        return RedirectResponse(url="/espacos/agenda", status_code=303)

    atribuicao = AgendaEspacoEquipa(
        espaco_id=espaco_id,
        equipa_id=equipa_id,
        data=data_obj,
        hora_inicio=hora_inicio,
        hora_fim=hora_fim,
        observacoes=observacoes or None,
    )
    db.add(atribuicao)
    db.commit()
    set_flash(request, "Espaço atribuído com sucesso.", "success")

    redirect_url = f"/espacos/agenda?equipa_id={equipa_id}"
    return RedirectResponse(url=redirect_url, status_code=303)


# ─────────────────────────────────────────
# APAGAR ATRIBUIÇÃO
# URL: POST /espacos/agenda/{id}/apagar
# ─────────────────────────────────────────
@router.post("/espacos/agenda/{atribuicao_id}/apagar")
async def apagar_atribuicao_espaco(
    atribuicao_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_coordenacao),
):
    atribuicao = db.query(AgendaEspacoEquipa).filter(AgendaEspacoEquipa.id == atribuicao_id).first()
    if atribuicao:
        equipa_id = atribuicao.equipa_id
        db.delete(atribuicao)
        db.commit()
        set_flash(request, "Atribuição removida.", "success")
        return RedirectResponse(url=f"/espacos/agenda?equipa_id={equipa_id}", status_code=303)
    return RedirectResponse(url="/espacos/agenda", status_code=303)


# ─────────────────────────────────────────
# API JSON — ESPAÇOS DISPONÍVEIS POR DATA
# URL: GET /api/espacos/disponiveis
# ─────────────────────────────────────────
@router.get("/api/espacos/disponiveis")
def api_espacos_disponiveis(
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
    equipa_id: int = Query(...),
    data: str = Query(...),
):
    try:
        data_obj = date_type.fromisoformat(data)
    except ValueError:
        return JSONResponse([])

    atribuicoes = (
        db.query(AgendaEspacoEquipa)
        .options(joinedload(AgendaEspacoEquipa.espaco))
        .filter(
            AgendaEspacoEquipa.equipa_id == equipa_id,
            AgendaEspacoEquipa.data == data_obj,
            AgendaEspacoEquipa.ativo == True,
        )
        .order_by(AgendaEspacoEquipa.hora_inicio)
        .all()
    )

    return JSONResponse([
        {
            "id": a.id,
            "espaco_id": a.espaco_id,
            "nome": a.espaco.nome,
            "hora_inicio": a.hora_inicio,
            "hora_fim": a.hora_fim,
        }
        for a in atribuicoes
        if a.espaco
    ])

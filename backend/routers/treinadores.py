from fastapi import APIRouter, Request, Depends, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from database import get_db
from models.treinador import Treinador
from models.equipa import Equipa

router = APIRouter(prefix="/treinadores")
templates = Jinja2Templates(directory="../frontend/templates")


def obter_utilizador_atual(request: Request, db: Session):
    from auth import verificar_token
    from models.utilizador import Utilizador
    token = request.session.get("token")
    if not token:
        return None
    payload = verificar_token(token)
    if not payload:
        return None
    return db.query(Utilizador).filter(
        Utilizador.username == payload.get("sub")
    ).first()


# --- LISTA DE TREINADORES ---
@router.get("", response_class=HTMLResponse)
def listar_treinadores(request: Request, db: Session = Depends(get_db)):
    utilizador = obter_utilizador_atual(request, db)
    if not utilizador:
        return RedirectResponse(url="/login")

    treinadores = db.query(Treinador).all()
    return templates.TemplateResponse(request, "treinadores/lista.html", {
        "utilizador": utilizador,
        "treinadores": treinadores
    })


# --- FORMULÁRIO DE CRIAR TREINADOR ---
@router.get("/novo", response_class=HTMLResponse)
def form_novo_treinador(request: Request, db: Session = Depends(get_db)):
    utilizador = obter_utilizador_atual(request, db)
    if not utilizador:
        return RedirectResponse(url="/login")

    equipas = db.query(Equipa).all()
    return templates.TemplateResponse(request, "treinadores/form.html", {
        "utilizador": utilizador,
        "equipas": equipas,
        "treinador": None
    })


# --- CRIAR TREINADOR ---
@router.post("/novo")
async def criar_treinador(
    request: Request,
    db: Session = Depends(get_db),
    nome: str = Form(...),
    data_nascimento: str = Form(""),
    morada: str = Form(""),
    telefone: str = Form(""),
    email: str = Form(""),
    numero_cedula: str = Form(""),
    numero_fpb: str = Form(""),
    observacoes: str = Form(""),
    equipas_ids: list[int] = Form(default=[])
):
    utilizador = obter_utilizador_atual(request, db)
    if not utilizador:
        return RedirectResponse(url="/login")

    from datetime import date
    treinador = Treinador(
        nome=nome,
        data_nascimento=date.fromisoformat(data_nascimento) if data_nascimento else None,
        morada=morada if morada else None,
        telefone=telefone if telefone else None,
        email=email if email else None,
        numero_cedula=numero_cedula if numero_cedula else None,
        numero_fpb=numero_fpb if numero_fpb else None,
        observacoes=observacoes if observacoes else None
    )

    # Associa as equipas seleccionadas
    if equipas_ids:
        equipas = db.query(Equipa).filter(Equipa.id.in_(equipas_ids)).all()
        treinador.equipas = equipas

    db.add(treinador)
    db.commit()

    return RedirectResponse(url="/treinadores", status_code=303)


# --- DETALHE DE UM TREINADOR ---
@router.get("/{treinador_id}", response_class=HTMLResponse)
def detalhe_treinador(treinador_id: int, request: Request, db: Session = Depends(get_db)):
    utilizador = obter_utilizador_atual(request, db)
    if not utilizador:
        return RedirectResponse(url="/login")

    treinador = db.query(Treinador).filter(Treinador.id == treinador_id).first()
    if not treinador:
        return RedirectResponse(url="/treinadores")

    return templates.TemplateResponse(request, "treinadores/detalhe.html", {
        "utilizador": utilizador,
        "treinador": treinador
    })
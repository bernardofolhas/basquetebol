from fastapi import APIRouter, Request, Depends, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from database import get_db
from models.equipa import Equipa, EscalaoEnum, GeneroEnum

# APIRouter é como um mini-FastAPI — tem rotas mas não é a aplicação principal
# O prefixo "/equipas" é adicionado automaticamente a todas as rotas deste router
router = APIRouter(prefix="/equipas")
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


# --- LISTA DE EQUIPAS ---
@router.get("", response_class=HTMLResponse)
def listar_equipas(request: Request, db: Session = Depends(get_db)):
    utilizador = obter_utilizador_atual(request, db)
    if not utilizador:
        return RedirectResponse(url="/login")

    equipas = db.query(Equipa).all()
    return templates.TemplateResponse(request, "equipas/lista.html", {
        "utilizador": utilizador,
        "equipas": equipas
    })


# --- FORMULÁRIO DE CRIAR EQUIPA ---
@router.get("/nova", response_class=HTMLResponse)
def form_nova_equipa(request: Request, db: Session = Depends(get_db)):
    utilizador = obter_utilizador_atual(request, db)
    if not utilizador:
        return RedirectResponse(url="/login")

    return templates.TemplateResponse(request, "equipas/form.html", {
        "utilizador": utilizador,
        "escaloes": EscalaoEnum,
        "generos": GeneroEnum,
        "equipa": None  # None indica que é criação, não edição
    })


# --- CRIAR EQUIPA ---
@router.post("/nova")
async def criar_equipa(
    request: Request,
    db: Session = Depends(get_db),
    nome: str = Form(...),
    escalao: str = Form(...),
    genero: str = Form(...),
    seccionista: str = Form("")
):
    utilizador = obter_utilizador_atual(request, db)
    if not utilizador:
        return RedirectResponse(url="/login")

    equipa = Equipa(
        nome=nome,
        escalao=escalao,
        genero=genero,
        seccionista=seccionista if seccionista else None
    )
    db.add(equipa)
    db.commit()

    return RedirectResponse(url="/equipas", status_code=303)
    # 303 = "See Other" — é o código correcto para redirecionar após um POST


# --- DETALHE DE UMA EQUIPA ---
@router.get("/{equipa_id}", response_class=HTMLResponse)
def detalhe_equipa(equipa_id: int, request: Request, db: Session = Depends(get_db)):
    utilizador = obter_utilizador_atual(request, db)
    if not utilizador:
        return RedirectResponse(url="/login")

    equipa = db.query(Equipa).filter(Equipa.id == equipa_id).first()
    if not equipa:
        return RedirectResponse(url="/equipas")

    return templates.TemplateResponse(request, "equipas/detalhe.html", {
        "utilizador": utilizador,
        "equipa": equipa
    })

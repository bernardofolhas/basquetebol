from fastapi import APIRouter, Request, Depends, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from database import get_db
from models.jogador import Jogador, RegistoAntropometrico
from models.equipa import Equipa

router = APIRouter(prefix="/jogadores")
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


# --- LISTA DE JOGADORES ---
@router.get("", response_class=HTMLResponse)
def listar_jogadores(request: Request, db: Session = Depends(get_db)):
    utilizador = obter_utilizador_atual(request, db)
    if not utilizador:
        return RedirectResponse(url="/login")

    jogadores = db.query(Jogador).all()
    return templates.TemplateResponse(request, "jogadores/lista.html", {
        "utilizador": utilizador,
        "jogadores": jogadores
    })


# --- FORMULÁRIO DE CRIAR JOGADOR ---
@router.get("/novo", response_class=HTMLResponse)
def form_novo_jogador(request: Request, db: Session = Depends(get_db)):
    utilizador = obter_utilizador_atual(request, db)
    if not utilizador:
        return RedirectResponse(url="/login")

    equipas = db.query(Equipa).all()
    return templates.TemplateResponse(request, "jogadores/form.html", {
        "utilizador": utilizador,
        "equipas": equipas,
        "jogador": None
    })


# --- CRIAR JOGADOR ---
@router.post("/novo")
async def criar_jogador(
    request: Request,
    db: Session = Depends(get_db),
    nome: str = Form(...),
    data_nascimento: str = Form(""),
    naturalidade: str = Form(""),
    morada: str = Form(""),
    numero_camisola: str = Form(""),
    posicao: str = Form(""),
    telefone: str = Form(""),
    email: str = Form(""),
    nome_pai: str = Form(""),
    telefone_pai: str = Form(""),
    email_pai: str = Form(""),
    nome_mae: str = Form(""),
    telefone_mae: str = Form(""),
    email_mae: str = Form(""),
    equipa_id: str = Form("")
):
    utilizador = obter_utilizador_atual(request, db)
    if not utilizador:
        return RedirectResponse(url="/login")

    from datetime import date
    jogador = Jogador(
        nome=nome,
        data_nascimento=date.fromisoformat(data_nascimento) if data_nascimento else None,
        naturalidade=naturalidade if naturalidade else None,
        morada=morada if morada else None,
        numero_camisola=int(numero_camisola) if numero_camisola else None,
        posicao=posicao if posicao else None,
        telefone=telefone if telefone else None,
        email=email if email else None,
        nome_pai=nome_pai if nome_pai else None,
        telefone_pai=telefone_pai if telefone_pai else None,
        email_pai=email_pai if email_pai else None,
        nome_mae=nome_mae if nome_mae else None,
        telefone_mae=telefone_mae if telefone_mae else None,
        email_mae=email_mae if email_mae else None,
        equipa_id=int(equipa_id) if equipa_id else None
    )

    db.add(jogador)
    db.commit()

    return RedirectResponse(url="/jogadores", status_code=303)


# --- DETALHE DE UM JOGADOR ---
@router.get("/{jogador_id}", response_class=HTMLResponse)
def detalhe_jogador(jogador_id: int, request: Request, db: Session = Depends(get_db)):
    utilizador = obter_utilizador_atual(request, db)
    if not utilizador:
        return RedirectResponse(url="/login")

    jogador = db.query(Jogador).filter(Jogador.id == jogador_id).first()
    if not jogador:
        return RedirectResponse(url="/jogadores")

    return templates.TemplateResponse(request, "jogadores/detalhe.html", {
        "utilizador": utilizador,
        "jogador": jogador
    })


# --- ADICIONAR REGISTO ANTROPOMÉTRICO ---
@router.post("/{jogador_id}/antropometria")
async def adicionar_antropometria(
    jogador_id: int,
    request: Request,
    db: Session = Depends(get_db),
    data: str = Form(...),
    altura: str = Form(""),
    peso: str = Form(""),
    envergadura: str = Form(""),
    altura_sentado: str = Form("")
):
    utilizador = obter_utilizador_atual(request, db)
    if not utilizador:
        return RedirectResponse(url="/login")

    from datetime import date
    registo = RegistoAntropometrico(
        jogador_id=jogador_id,
        data=date.fromisoformat(data),
        altura=altura if altura else None,
        peso=peso if peso else None,
        envergadura=envergadura if envergadura else None,
        altura_sentado=altura_sentado if altura_sentado else None
    )

    db.add(registo)
    db.commit()

    return RedirectResponse(url=f"/jogadores/{jogador_id}", status_code=303)
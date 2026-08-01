from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from template_config import Jinja2Templates
from sqlalchemy.orm import Session, joinedload

from auth import encriptar_password, verificar_perfil
from auth_deps import exigir_admin, exigir_autenticacao, exigir_coordenacao
from database import get_db
from flash import set_flash
from models.equipa import Equipa
from models.treinador import Treinador
from models.utilizador import PerfilEnum, Utilizador
from paths import TEMPLATES_DIR

router = APIRouter(prefix="/treinadores")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("", response_class=HTMLResponse)
def listar_treinadores(
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    treinadores = db.query(Treinador).options(joinedload(Treinador.equipas)).all()
    return templates.TemplateResponse(request, "treinadores/lista.html", {
        "utilizador": utilizador,
        "treinadores": treinadores,
    })


@router.get("/novo", response_class=HTMLResponse)
def form_novo_treinador(
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    if not verificar_perfil(utilizador, ["administrador", "coordenador"]):
        return RedirectResponse(url="/treinadores", status_code=302)
    equipas = db.query(Equipa).all()
    return templates.TemplateResponse(request, "treinadores/form.html", {
        "utilizador": utilizador,
        "equipas": equipas,
        "treinador": None,
        "erro": None,
    })


@router.post("/novo")
async def criar_treinador(
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
    nome: str = Form(...),
    data_nascimento: str = Form(""),
    morada: str = Form(""),
    telefone: str = Form(""),
    email: str = Form(""),
    numero_cedula: str = Form(""),
    numero_fpb: str = Form(""),
    observacoes: str = Form(""),
    equipas_ids: list[int] = Form(default=[]),
    login_username: str = Form(""),
    login_password: str = Form(""),
):
    if not verificar_perfil(utilizador, ["administrador", "coordenador"]):
        return RedirectResponse(url="/treinadores", status_code=302)
    # Validar username/password se fornecidos
    if login_username or login_password:
        if not login_username or not login_password:
            equipas = db.query(Equipa).all()
            return templates.TemplateResponse(request, "treinadores/form.html", {
                "utilizador": utilizador,
                "equipas": equipas,
                "treinador": None,
                "erro": "Preenche o username e a password para criar o login.",
            })
        if len(login_password) < 8:
            equipas = db.query(Equipa).all()
            return templates.TemplateResponse(request, "treinadores/form.html", {
                "utilizador": utilizador,
                "equipas": equipas,
                "treinador": None,
                "erro": "A password deve ter pelo menos 8 caracteres.",
            })
        if db.query(Utilizador).filter(Utilizador.username == login_username).first():
            equipas = db.query(Equipa).all()
            return templates.TemplateResponse(request, "treinadores/form.html", {
                "utilizador": utilizador,
                "equipas": equipas,
                "treinador": None,
                "erro": f"O username '{login_username}' já está em uso.",
            })

    treinador = Treinador(
        nome=nome,
        data_nascimento=date.fromisoformat(data_nascimento) if data_nascimento else None,
        morada=morada or None,
        telefone=telefone or None,
        email=email or None,
        numero_cedula=numero_cedula or None,
        numero_fpb=numero_fpb or None,
        observacoes=observacoes or None,
    )

    if equipas_ids:
        treinador.equipas = db.query(Equipa).filter(Equipa.id.in_(equipas_ids)).all()

    db.add(treinador)
    db.flush()  # gera o treinador.id sem fechar a transação

    if login_username and login_password:
        db.add(Utilizador(
            nome=nome,
            username=login_username,
            email=email or f"{login_username}@treinador.local",
            password_hash=encriptar_password(login_password),
            perfil=PerfilEnum.treinador,
            treinador_id=treinador.id,
        ))

    db.commit()
    set_flash(request, f"Treinador '{nome}' criado com sucesso.")
    return RedirectResponse(url="/treinadores", status_code=303)


@router.get("/{treinador_id}", response_class=HTMLResponse)
def detalhe_treinador(
    treinador_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    treinador = db.query(Treinador).options(
        joinedload(Treinador.equipas)
    ).filter(Treinador.id == treinador_id).first()
    if not treinador:
        return RedirectResponse(url="/treinadores")

    return templates.TemplateResponse(request, "treinadores/detalhe.html", {
        "utilizador": utilizador,
        "treinador": treinador,
    })


@router.get("/{treinador_id}/editar", response_class=HTMLResponse)
def form_editar_treinador(
    treinador_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_coordenacao),
):
    treinador = db.query(Treinador).filter(Treinador.id == treinador_id).first()
    if not treinador:
        return RedirectResponse(url="/treinadores")

    equipas = db.query(Equipa).all()
    return templates.TemplateResponse(request, "treinadores/form.html", {
        "utilizador": utilizador,
        "treinador": treinador,
        "equipas": equipas,
    })


@router.post("/{treinador_id}/editar")
async def editar_treinador(
    treinador_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_coordenacao),
    nome: str = Form(...),
    data_nascimento: str = Form(""),
    morada: str = Form(""),
    telefone: str = Form(""),
    email: str = Form(""),
    numero_cedula: str = Form(""),
    numero_fpb: str = Form(""),
    observacoes: str = Form(""),
    equipas_ids: list[int] = Form(default=[]),
):
    treinador = db.query(Treinador).filter(Treinador.id == treinador_id).first()
    if not treinador:
        return RedirectResponse(url="/treinadores")

    treinador.nome = nome
    treinador.data_nascimento = date.fromisoformat(data_nascimento) if data_nascimento else None
    treinador.morada = morada or None
    treinador.telefone = telefone or None
    treinador.email = email or None
    treinador.numero_cedula = numero_cedula or None
    treinador.numero_fpb = numero_fpb or None
    treinador.observacoes = observacoes or None
    treinador.equipas = db.query(Equipa).filter(Equipa.id.in_(equipas_ids)).all() if equipas_ids else []

    db.commit()
    set_flash(request, f"Treinador '{nome}' atualizado com sucesso.")
    return RedirectResponse(url=f"/treinadores/{treinador_id}", status_code=303)


@router.post("/{treinador_id}/apagar")
def apagar_treinador(
    treinador_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_admin),
):
    treinador = db.query(Treinador).filter(Treinador.id == treinador_id).first()
    if treinador:
        nome = treinador.nome
        db.delete(treinador)
        db.commit()
        set_flash(request, f"Treinador '{nome}' apagado.")

    return RedirectResponse(url="/treinadores", status_code=303)

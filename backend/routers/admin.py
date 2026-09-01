from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from template_config import Jinja2Templates
from sqlalchemy.orm import Session

from auth import encriptar_password
from auth_deps import exigir_admin
from database import get_db
from flash import set_flash
from models.treinador import Treinador
from models.equipa import Equipa
from models.utilizador import PerfilEnum, Utilizador
from paths import TEMPLATES_DIR
from models.auditoria import RegistoAuditoria
from config import config
from models.recuperacao_password import TokenRecuperacaoPassword
from services.recuperacao_password_service import criar_token_recuperacao

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _contexto_formulario_utilizador(db: Session, utilizador, utilizador_editar=None, erro=None, modo=None):
    """Mantém o formulário de contas coerente para perfis e equipas de staff."""
    return {
        "utilizador": utilizador,
        "utilizador_editar": utilizador_editar,
        "perfis": [p for p in PerfilEnum if p != PerfilEnum.superadministrador],
        "treinadores": db.query(Treinador).order_by(Treinador.nome).all(),
        "equipas": db.query(Equipa).order_by(Equipa.nome).all(),
        "erro": erro,
        "modo": modo,
    }


def _equipas_staff_selecionadas(db: Session, equipa_ids: list[str], clube_id: int | None) -> list[Equipa]:
    ids = sorted({int(item) for item in equipa_ids if str(item).isdigit()})
    if not ids:
        return []
    equipas = db.query(Equipa).filter(Equipa.id.in_(ids)).all()
    if len(equipas) != len(ids) or any(equipa.clube_id != clube_id for equipa in equipas):
        raise ValueError("Seleciona apenas equipas do teu clube para a conta de staff.")
    return equipas


@router.get("/auditoria", response_class=HTMLResponse)
def listar_auditoria(
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_admin),
):
    registos = db.query(RegistoAuditoria).order_by(RegistoAuditoria.criado_em.desc()).limit(250).all()
    return templates.TemplateResponse(request, "admin/auditoria.html", {
        "utilizador": utilizador,
        "registos": registos,
    })


@router.get("/utilizadores", response_class=HTMLResponse)
def listar_utilizadores(
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_admin),
):
    utilizadores = db.query(Utilizador).order_by(Utilizador.nome).all()
    return templates.TemplateResponse(request, "admin/utilizadores_lista.html", {
        "utilizador": utilizador,
        "utilizadores": utilizadores,
    })


@router.post("/utilizadores/{utilizador_id}/recuperacao-temporaria", response_class=HTMLResponse)
def gerar_recuperacao_temporaria(
    utilizador_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin=Depends(exigir_admin),
):
    alvo = db.query(Utilizador).filter(Utilizador.id == utilizador_id).first()
    if not alvo or alvo.clube_id != admin.clube_id:
        return RedirectResponse("/admin/utilizadores", status_code=303)
    db.query(TokenRecuperacaoPassword).filter(
        TokenRecuperacaoPassword.utilizador_id == alvo.id,
        TokenRecuperacaoPassword.tipo == "administrativo",
        TokenRecuperacaoPassword.utilizado_em.is_(None),
    ).update({"utilizado_em": datetime.now()}, synchronize_session=False)
    token, registo = criar_token_recuperacao(
        db, alvo, tipo="administrativo", criado_por=admin,
        pedido_ip=getattr(request.client, "host", None),
    )
    from services.auditoria_service import registar_auditoria
    registar_auditoria(
        db, admin, "gerar_acesso_temporario", "utilizador", alvo.id,
        f"Acesso temporário iniciado para {alvo.username}; expira em {registo.expira_em:%d/%m/%Y %H:%M}.", request,
    )
    db.commit()
    return templates.TemplateResponse(request, "admin/recuperacao_temporaria.html", {
        "utilizador": admin,
        "alvo": alvo,
        "ligacao_temporaria": f"{config.app_base_url}/acesso-temporario/{token}",
        "criado_em": registo.criado_em,
        "expira_em": registo.expira_em,
    })


@router.get("/utilizadores/novo", response_class=HTMLResponse)
def form_novo_utilizador(
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_admin),
):
    return templates.TemplateResponse(request, "admin/utilizadores_form.html", _contexto_formulario_utilizador(db, utilizador))


@router.post("/utilizadores/novo")
async def criar_utilizador(
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_admin),
    username: str = Form(...),
    password: str = Form(...),
    nome: str = Form(...),
    email: str = Form(...),
    perfil: str = Form(...),
    treinador_id: str = Form(""),
    equipa_ids: list[str] = Form([]),
):
    existe_username = db.query(Utilizador).filter(Utilizador.username == username).first()
    if existe_username:
        return templates.TemplateResponse(request, "admin/utilizadores_form.html", _contexto_formulario_utilizador(db, utilizador, erro="Já existe um utilizador com esse username."))

    existe_email = db.query(Utilizador).filter(Utilizador.email == email).first()
    if existe_email:
        return templates.TemplateResponse(request, "admin/utilizadores_form.html", _contexto_formulario_utilizador(db, utilizador, erro="Já existe um utilizador com esse email."))

    try:
        perfil_enum = PerfilEnum(perfil)
        equipas_staff = _equipas_staff_selecionadas(db, equipa_ids, utilizador.clube_id) if perfil_enum == PerfilEnum.staff else []
    except ValueError as erro:
        return templates.TemplateResponse(request, "admin/utilizadores_form.html", _contexto_formulario_utilizador(db, utilizador, erro=str(erro)))

    novo_utilizador = Utilizador(
        username=username,
        password_hash=encriptar_password(password),
        nome=nome,
        email=email,
        perfil=perfil_enum,
        treinador_id=int(treinador_id) if treinador_id else None,
    )
    novo_utilizador.equipas_staff = equipas_staff

    db.add(novo_utilizador)
    from services.auditoria_service import registar_auditoria
    registar_auditoria(db, utilizador, "criar", "utilizador", None, f"Username: {username}", request)
    db.commit()
    set_flash(request, f"Utilizador '{username}' criado com sucesso.")
    return RedirectResponse(url="/admin/utilizadores", status_code=303)


@router.get("/utilizadores/{utilizador_id}/editar", response_class=HTMLResponse)
def form_editar_utilizador(
    utilizador_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_admin),
):
    utilizador_editar = db.query(Utilizador).filter(Utilizador.id == utilizador_id).first()
    if not utilizador_editar:
        return RedirectResponse(url="/admin/utilizadores", status_code=303)

    return templates.TemplateResponse(request, "admin/utilizadores_form.html", _contexto_formulario_utilizador(db, utilizador, utilizador_editar, modo="editar"))


@router.post("/utilizadores/{utilizador_id}/editar")
async def editar_utilizador(
    utilizador_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin=Depends(exigir_admin),
    username: str = Form(...),
    nome: str = Form(...),
    email: str = Form(...),
    perfil: str = Form(...),
    treinador_id: str = Form(""),
    equipa_ids: list[str] = Form([]),
    ativo: str = Form("true"),
    password: str = Form(""),
):
    utilizador_editar = db.query(Utilizador).filter(Utilizador.id == utilizador_id).first()
    if not utilizador_editar:
        return RedirectResponse(url="/admin/utilizadores", status_code=303)

    existe_username = db.query(Utilizador).filter(
        Utilizador.username == username,
        Utilizador.id != utilizador_id,
    ).first()
    if existe_username:
        return templates.TemplateResponse(request, "admin/utilizadores_form.html", _contexto_formulario_utilizador(db, admin, utilizador_editar, "Já existe outro utilizador com esse username.", "editar"))

    existe_email = db.query(Utilizador).filter(
        Utilizador.email == email,
        Utilizador.id != utilizador_id,
    ).first()
    if existe_email:
        return templates.TemplateResponse(request, "admin/utilizadores_form.html", _contexto_formulario_utilizador(db, admin, utilizador_editar, "Já existe outro utilizador com esse email.", "editar"))

    try:
        perfil_enum = PerfilEnum(perfil)
        equipas_staff = _equipas_staff_selecionadas(db, equipa_ids, admin.clube_id) if perfil_enum == PerfilEnum.staff else []
    except ValueError as erro:
        return templates.TemplateResponse(request, "admin/utilizadores_form.html", _contexto_formulario_utilizador(db, admin, utilizador_editar, str(erro), "editar"))

    utilizador_editar.username = username
    utilizador_editar.nome = nome
    utilizador_editar.email = email
    utilizador_editar.perfil = perfil_enum
    utilizador_editar.ativo = (ativo == "true")
    utilizador_editar.treinador_id = int(treinador_id) if treinador_id else None
    utilizador_editar.equipas_staff = equipas_staff

    if password and password.strip():
        utilizador_editar.password_hash = encriptar_password(password)

    from services.auditoria_service import registar_auditoria
    registar_auditoria(db, admin, "editar", "utilizador", utilizador_id, f"Username: {username}", request)
    db.commit()
    set_flash(request, f"Utilizador '{username}' atualizado com sucesso.")
    return RedirectResponse(url="/admin/utilizadores", status_code=303)


@router.post("/utilizadores/{utilizador_id}/apagar")
async def apagar_utilizador(
    utilizador_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin=Depends(exigir_admin),
):
    utilizador_apagar = db.query(Utilizador).filter(Utilizador.id == utilizador_id).first()

    if not utilizador_apagar:
        return RedirectResponse(url="/admin/utilizadores", status_code=303)

    if utilizador_apagar.id == admin.id:
        set_flash(request, "Não podes apagar a tua própria conta.", tipo="error")
        return RedirectResponse(url="/admin/utilizadores", status_code=303)

    nome = utilizador_apagar.username
    from services.auditoria_service import registar_auditoria
    registar_auditoria(db, admin, "apagar", "utilizador", utilizador_id, f"Username: {nome}", request)
    db.delete(utilizador_apagar)
    db.commit()
    set_flash(request, f"Utilizador '{nome}' apagado.")
    return RedirectResponse(url="/admin/utilizadores", status_code=303)

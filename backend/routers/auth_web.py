from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from template_config import Jinja2Templates
from sqlalchemy.orm import Session

from auth import criar_token, encriptar_password, verificar_password
from auth_deps import NaoAutenticado, exigir_autenticacao
from database import get_db
from flash import set_flash
from limiter import limiter
from paths import TEMPLATES_DIR
from services.auditoria_service import registar_auditoria

router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("/login", response_class=HTMLResponse)
def pagina_login(request: Request, db: Session = Depends(get_db)):
    """Apresenta sempre a página de login e limpa sessões antigas."""
    request.session.clear()
    return templates.TemplateResponse(request, "login.html")


@router.post("/login-form")
@limiter.limit("10/minute")
async def processar_login(
    request: Request,
    db: Session = Depends(get_db),
    username: str = Form(...),
    password: str = Form(...),
):
    """Autentica o utilizador e inicia a sessão web."""
    from models.utilizador import Utilizador

    utilizador = db.query(Utilizador).filter(
        Utilizador.username == username
    ).first()

    if not utilizador or not verificar_password(password, utilizador.password_hash):
        return templates.TemplateResponse(request, "login.html", {
            "erro": "Username ou password incorretos."
        })

    if not utilizador.ativo:
        return templates.TemplateResponse(request, "login.html", {
            "erro": "Conta desativada. Contacta o administrador."
        })

    token = criar_token({
        "sub": utilizador.username,
        "perfil": utilizador.perfil.value
    })

    request.session["token"] = token
    registar_auditoria(
        db,
        utilizador,
        "login",
        "sessao_web",
        detalhes="Login efetuado com sucesso.",
        request=request,
    )
    db.commit()
    return RedirectResponse(url="/dashboard", status_code=303)


@router.get("/logout")
def logout_get(request: Request):
    """Mantém compatibilidade com o logout via GET."""
    request.session.clear()
    return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)


@router.post("/logout")
def logout_post(request: Request):
    """Fluxo principal de logout via POST."""
    request.session.clear()
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)


# ─────────────────────────────────────────────────────────────
# PÁGINA DE CONTA DO UTILIZADOR — ALTERAR PASSWORD
# ─────────────────────────────────────────────────────────────

@router.get("/minha-conta", response_class=HTMLResponse)
def pagina_minha_conta(
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    """Apresenta a página de conta do utilizador com opção de alterar password."""
    return templates.TemplateResponse(request, "minha_conta.html", {
        "utilizador": utilizador,
    })


@router.post("/minha-conta/alterar-password")
async def alterar_password(
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
    password_atual: str = Form(...),
    password_nova: str = Form(...),
    password_confirmar: str = Form(...),
):
    """Altera a password do utilizador autenticado."""
    erros = []

    if not verificar_password(password_atual, utilizador.password_hash):
        erros.append("A password atual está incorreta.")

    if len(password_nova) < 8:
        erros.append("A nova password deve ter pelo menos 8 caracteres.")

    if password_nova != password_confirmar:
        erros.append("A nova password e a confirmação não coincidem.")

    if erros:
        return templates.TemplateResponse(request, "minha_conta.html", {
            "utilizador": utilizador,
            "erros": erros,
        })

    utilizador.password_hash = encriptar_password(password_nova)
    utilizador.deve_alterar_password = False
    db.commit()

    set_flash(request, "Password alterada com sucesso.")
    return RedirectResponse(url="/minha-conta", status_code=303)

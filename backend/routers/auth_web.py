from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from template_config import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from auth import criar_token, encriptar_password, verificar_password
from auth_deps import NaoAutenticado, exigir_autenticacao
from database import get_db
from flash import set_flash
from limiter import limiter
from paths import TEMPLATES_DIR
from services.auditoria_service import registar_auditoria
from config import config
from models.recuperacao_password import TokenRecuperacaoPassword
from models.utilizador import Utilizador
from services.email_service import enviar_email
from services.recuperacao_password_service import (
    consumir_token,
    criar_token_recuperacao,
    obter_token_valido,
    validar_password,
)

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
        "perfil": utilizador.perfil.value,
        "sv": utilizador.sessao_versao or 0,
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
    destino = "/questionarios/disponiveis" if utilizador.perfil.value == "atleta" else "/dashboard"
    return RedirectResponse(url=destino, status_code=303)


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


MENSAGEM_RECUPERACAO = "Se os dados corresponderem a uma conta ativa, receberás uma ligação de recuperação por email."


@router.get("/recuperar-password", response_class=HTMLResponse)
def pagina_pedir_recuperacao(request: Request):
    return templates.TemplateResponse(request, "recuperar_password_pedido.html")


@router.post("/recuperar-password")
@limiter.limit("5/hour")
async def pedir_recuperacao_password(
    request: Request,
    identificador: str = Form(...),
    db: Session = Depends(get_db),
):
    valor = identificador.strip().lower()
    utilizador = db.query(Utilizador).execution_options(ignorar_clube=True).filter(
        (func.lower(Utilizador.email) == valor) | (func.lower(Utilizador.username) == valor),
        Utilizador.ativo.is_(True),
    ).first()
    if utilizador and utilizador.email and "@" in utilizador.email:
        db.query(TokenRecuperacaoPassword).execution_options(ignorar_clube=True).filter(
            TokenRecuperacaoPassword.utilizador_id == utilizador.id,
            TokenRecuperacaoPassword.tipo == "email",
            TokenRecuperacaoPassword.utilizado_em.is_(None),
        ).update({"utilizado_em": func.now()}, synchronize_session=False)
        token, _ = criar_token_recuperacao(
            db, utilizador, pedido_ip=getattr(request.client, "host", None),
        )
        registar_auditoria(
            db, utilizador, "pedir_recuperacao_password", "utilizador", utilizador.id,
            detalhes="Pedido de recuperação por email.", request=request,
        )
        ligacao = f"{config.app_base_url}/redefinir-password/{token}"
        enviar_email(
            utilizador.email,
            "Recuperação da palavra-passe",
            f"Foi pedida a recuperação da tua conta. A ligação é válida durante 30 minutos e só pode ser utilizada uma vez:\n\n{ligacao}\n\nSe não fizeste este pedido, ignora esta mensagem.",
        )
        db.commit()
    return templates.TemplateResponse(request, "recuperar_password_pedido.html", {
        "mensagem": MENSAGEM_RECUPERACAO,
    })


@router.get("/redefinir-password/{token}", response_class=HTMLResponse)
def pagina_redefinir_password(token: str, request: Request, db: Session = Depends(get_db)):
    registo = obter_token_valido(db, token, tipo="email", bloquear=True)
    return templates.TemplateResponse(request, "recuperar_password_redefinir.html", {
        "token": token if registo else None,
        "token_invalido": not bool(registo),
    })


@router.post("/redefinir-password/{token}")
@limiter.limit("10/hour")
async def redefinir_password(
    token: str,
    request: Request,
    password_nova: str = Form(...),
    password_confirmar: str = Form(...),
    db: Session = Depends(get_db),
):
    registo = obter_token_valido(db, token, tipo="email")
    if not registo:
        return templates.TemplateResponse(request, "recuperar_password_redefinir.html", {
            "token": None, "token_invalido": True,
        }, status_code=400)
    erros = validar_password(password_nova)
    if password_nova != password_confirmar:
        erros.append("A palavra-passe e a confirmação não coincidem.")
    if erros:
        return templates.TemplateResponse(request, "recuperar_password_redefinir.html", {
            "token": token, "erros": erros, "token_invalido": False,
        }, status_code=422)
    utilizador = registo.utilizador
    utilizador.password_hash = encriptar_password(password_nova)
    utilizador.sessao_versao = (utilizador.sessao_versao or 0) + 1
    utilizador.deve_alterar_password = False
    consumir_token(registo)
    registar_auditoria(db, utilizador, "recuperar_password_email", "utilizador", utilizador.id, request=request)
    db.commit()
    enviar_email(
        utilizador.email,
        "Palavra-passe alterada",
        "A palavra-passe da tua conta foi alterada. Se não reconheces esta ação, contacta imediatamente o administrador do clube.",
    )
    request.session.clear()
    return templates.TemplateResponse(request, "recuperar_password_concluida.html")


@router.get("/acesso-temporario/{token}")
def usar_acesso_temporario(token: str, request: Request, db: Session = Depends(get_db)):
    registo = obter_token_valido(db, token, tipo="administrativo")
    if not registo or not registo.utilizador.ativo:
        set_flash(request, "A ligação temporária é inválida ou expirou.", "error")
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(request, "acesso_temporario_confirmar.html", {
        "token": token,
        "utilizador_alvo": registo.utilizador,
    })


@router.post("/acesso-temporario/{token}")
@limiter.limit("10/hour")
async def confirmar_acesso_temporario(token: str, request: Request, db: Session = Depends(get_db)):
    registo = obter_token_valido(db, token, tipo="administrativo", bloquear=True)
    if not registo or not registo.utilizador.ativo:
        set_flash(request, "A ligação temporária é inválida ou expirou.", "error")
        return RedirectResponse("/login", status_code=303)
    utilizador = registo.utilizador
    consumir_token(registo)
    utilizador.deve_alterar_password = True
    utilizador.sessao_versao = (utilizador.sessao_versao or 0) + 1
    registar_auditoria(
        db, utilizador, "usar_acesso_temporario", "utilizador", utilizador.id,
        detalhes=f"Acesso temporário administrativo {registo.id} utilizado.", request=request,
    )
    db.commit()
    request.session.clear()
    request.session["token"] = criar_token({
        "sub": utilizador.username,
        "perfil": utilizador.perfil.value,
        "sv": utilizador.sessao_versao,
    })
    return RedirectResponse("/minha-conta", status_code=303)


@router.post("/minha-conta/alterar-password")
async def alterar_password(
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
    password_atual: str = Form(""),
    password_nova: str = Form(...),
    password_confirmar: str = Form(...),
):
    """Altera a password do utilizador autenticado."""
    erros = []

    if not utilizador.deve_alterar_password and not verificar_password(password_atual, utilizador.password_hash):
        erros.append("A password atual está incorreta.")
    erros.extend(validar_password(password_nova))

    if password_nova != password_confirmar:
        erros.append("A nova password e a confirmação não coincidem.")

    if erros:
        return templates.TemplateResponse(request, "minha_conta.html", {
            "utilizador": utilizador,
            "erros": erros,
        })

    utilizador.password_hash = encriptar_password(password_nova)
    utilizador.deve_alterar_password = False
    utilizador.sessao_versao = (utilizador.sessao_versao or 0) + 1
    registar_auditoria(db, utilizador, "alterar_password", "utilizador", utilizador.id, request=request)
    db.commit()
    enviar_email(utilizador.email, "Palavra-passe alterada", "A palavra-passe da tua conta foi alterada com sucesso.")
    request.session.clear()
    set_flash(request, "Palavra-passe alterada. Inicia sessão novamente.")
    return RedirectResponse(url="/login", status_code=303)

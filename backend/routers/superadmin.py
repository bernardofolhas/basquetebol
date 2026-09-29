import json
import re

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from template_config import Jinja2Templates
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from auth import encriptar_password
from auth_deps import exigir_superadmin
from clube_contexto import definir_clube_atual, repor_clube_atual
from database import get_db
from flash import set_flash
from models.clube import Clube, EstadoClubeEnum
from models.identidade_clube import IdentidadeClube
from models.utilizador import PerfilEnum, Utilizador
from paths import TEMPLATES_DIR
from services.auditoria_service import registar_auditoria
from services.identidade_clube_service import normalizar_cor
from config import config
from logging_config import obter_logger
from models.recuperacao_password import TokenRecuperacaoPassword
from services.recuperacao_password_service import criar_token_recuperacao
from routers.identidade import _apagar_logo, _guardar_logo

router = APIRouter(prefix="/superadmin")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
logger = obter_logger(__name__)


def _slug(valor: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", valor.lower()).strip("-")


@router.get("/clubes", response_class=HTMLResponse)
def listar_clubes(request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_superadmin)):
    clubes = db.query(Clube).execution_options(ignorar_clube=True).order_by(Clube.nome_oficial).all()
    return templates.TemplateResponse(request, "superadmin/clubes.html", {"utilizador": utilizador, "clubes": clubes})


@router.get("/utilizadores", response_class=HTMLResponse)
def listar_utilizadores_globais(request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_superadmin)):
    utilizadores = db.query(Utilizador).execution_options(ignorar_clube=True).order_by(
        Utilizador.clube_id, Utilizador.nome,
    ).all()
    return templates.TemplateResponse(request, "superadmin/utilizadores.html", {
        "utilizador": utilizador, "utilizadores": utilizadores,
    })


@router.post("/utilizadores/{utilizador_id}/recuperacao-temporaria", response_class=HTMLResponse)
def gerar_recuperacao_temporaria_global(
    utilizador_id: int, request: Request, db: Session = Depends(get_db),
    utilizador=Depends(exigir_superadmin),
):
    alvo = db.query(Utilizador).execution_options(ignorar_clube=True).filter(Utilizador.id == utilizador_id).first()
    if not alvo or alvo.id == utilizador.id:
        return RedirectResponse("/superadmin/utilizadores", status_code=303)
    from datetime import datetime
    db.query(TokenRecuperacaoPassword).execution_options(ignorar_clube=True).filter(
        TokenRecuperacaoPassword.utilizador_id == alvo.id,
        TokenRecuperacaoPassword.tipo == "administrativo",
        TokenRecuperacaoPassword.utilizado_em.is_(None),
    ).update({"utilizado_em": datetime.now()}, synchronize_session=False)
    token, registo = criar_token_recuperacao(
        db, alvo, tipo="administrativo", criado_por=utilizador,
        pedido_ip=getattr(request.client, "host", None),
    )
    registar_auditoria(
        db, utilizador, "gerar_acesso_temporario", "utilizador", alvo.id,
        f"Recuperação global para {alvo.username}; clube {alvo.clube_id}; expira em {registo.expira_em:%d/%m/%Y %H:%M}.", request,
    )
    db.commit()
    return templates.TemplateResponse(request, "superadmin/recuperacao_temporaria.html", {
        "utilizador": utilizador, "alvo": alvo,
        "ligacao_temporaria": f"{config.app_base_url}/acesso-temporario/{token}",
        "criado_em": registo.criado_em,
        "expira_em": registo.expira_em,
    })


@router.get("/clubes/novo", response_class=HTMLResponse)
def novo_clube(request: Request, utilizador=Depends(exigir_superadmin)):
    return templates.TemplateResponse(request, "superadmin/clube_form.html", {"utilizador": utilizador, "erro": None})


def _obter_clube_global(db: Session, clube_id: int) -> Clube | None:
    return db.query(Clube).execution_options(ignorar_clube=True).filter(Clube.id == clube_id).first()


@router.get("/clubes/{clube_id}/editar", response_class=HTMLResponse)
def editar_clube_form(
    clube_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_superadmin),
):
    clube = _obter_clube_global(db, clube_id)
    if not clube:
        set_flash(request, "Clube não encontrado.", "error")
        return RedirectResponse("/superadmin/clubes", status_code=303)
    return templates.TemplateResponse(request, "superadmin/clube_editar.html", {
        "utilizador": utilizador,
        "clube": clube,
        "erro": None,
    })


@router.post("/clubes/{clube_id}/editar")
async def editar_clube(
    clube_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_superadmin),
    nome_oficial: str = Form(...),
    nome_curto: str = Form(...),
    identificador: str = Form(...),
    cor_principal: str = Form("#f97316"),
    cor_secundaria: str = Form("#1f2937"),
    cor_destaque: str = Form("#0ea5e9"),
    epoca_inicial: str = Form(""),
    estado: str = Form("ativo"),
    logo_principal: UploadFile | None = File(None),
    logo_secundario: UploadFile | None = File(None),
    remover_logo_principal: str = Form("false"),
    remover_logo_secundario: str = Form("false"),
):
    clube = _obter_clube_global(db, clube_id)
    if not clube:
        return RedirectResponse("/superadmin/clubes", status_code=303)
    identificador_normalizado = _slug(identificador)
    duplicado = db.query(Clube).execution_options(ignorar_clube=True).filter(
        Clube.identificador == identificador_normalizado,
        Clube.id != clube.id,
    ).first()
    erro = None
    if not nome_oficial.strip() or not nome_curto.strip() or not identificador_normalizado:
        erro = "Preenche o nome oficial, nome curto e identificador."
    elif duplicado:
        erro = "Já existe outro clube com este identificador."
    elif estado not in {item.value for item in EstadoClubeEnum}:
        erro = "O estado indicado não é válido."
    if erro:
        return templates.TemplateResponse(request, "superadmin/clube_editar.html", {
            "utilizador": utilizador, "clube": clube, "erro": erro,
        }, status_code=422)

    try:
        if remover_logo_principal == "true":
            _apagar_logo(clube.logo_principal)
            clube.logo_principal = None
        if remover_logo_secundario == "true":
            _apagar_logo(clube.logo_secundario)
            clube.logo_secundario = None
        novo_principal = await _guardar_logo(logo_principal, f"clube-{clube.id}-logo-principal")
        novo_secundario = await _guardar_logo(logo_secundario, f"clube-{clube.id}-logo-secundario")
        if novo_principal:
            clube.logo_principal = novo_principal
        if novo_secundario:
            clube.logo_secundario = novo_secundario
    except ValueError as exc:
        db.rollback()
        return templates.TemplateResponse(request, "superadmin/clube_editar.html", {
            "utilizador": utilizador, "clube": clube, "erro": str(exc),
        }, status_code=422)

    clube.nome_oficial = nome_oficial.strip()
    clube.nome_curto = nome_curto.strip()
    clube.identificador = identificador_normalizado
    clube.cor_principal = normalizar_cor(cor_principal, "#f97316")
    clube.cor_secundaria = normalizar_cor(cor_secundaria, "#1f2937")
    clube.cor_destaque = normalizar_cor(cor_destaque, "#0ea5e9")
    clube.epoca_inicial = epoca_inicial.strip() or None
    clube.estado = EstadoClubeEnum(estado)
    clube.tema_gerado = json.dumps({"principal": clube.cor_principal})

    identidade = db.query(IdentidadeClube).execution_options(ignorar_clube=True).filter(
        IdentidadeClube.clube_id == clube.id
    ).first()
    if not identidade:
        identidade = IdentidadeClube(clube_id=clube.id)
        db.add(identidade)
    identidade.nome_oficial = clube.nome_oficial
    identidade.nome_curto = clube.nome_curto
    identidade.logo_principal = clube.logo_principal
    identidade.logo_secundario = clube.logo_secundario
    identidade.cor_principal = clube.cor_principal
    identidade.cor_secundaria = clube.cor_secundaria
    identidade.cor_destaque = clube.cor_destaque
    identidade.epoca_predefinida = clube.epoca_inicial
    registar_auditoria(db, utilizador, "editar_clube", "clube", clube.id, f"Clube {clube.identificador}", request)
    db.commit()
    set_flash(request, "Clube atualizado com sucesso.")
    return RedirectResponse("/superadmin/clubes", status_code=303)


def _dados_operacionais_clube(db: Session, clube_id: int) -> list[tuple[str, int]]:
    ignoradas = {"clubes", "utilizadores", "identidade_clube", "registos_auditoria", "alembic_version"}
    resultado = []
    inspector = inspect(db.get_bind())
    for tabela in inspector.get_table_names():
        if tabela in ignoradas:
            continue
        if "clube_id" not in {coluna["name"] for coluna in inspector.get_columns(tabela)}:
            continue
        total = db.execute(
            text(f'SELECT COUNT(*) FROM "{tabela}" WHERE clube_id = :clube_id'),
            {"clube_id": clube_id},
        ).scalar_one()
        if total:
            resultado.append((tabela, total))
    return resultado


@router.post("/clubes/{clube_id}/eliminar")
def eliminar_clube(
    clube_id: int,
    request: Request,
    confirmacao: str = Form(...),
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_superadmin),
):
    clube = _obter_clube_global(db, clube_id)
    if not clube:
        return RedirectResponse("/superadmin/clubes", status_code=303)
    if confirmacao.strip() != clube.identificador:
        set_flash(request, "A confirmação não corresponde ao identificador do clube.", "error")
        return RedirectResponse(f"/superadmin/clubes/{clube.id}/editar", status_code=303)
    dados = _dados_operacionais_clube(db, clube.id)
    if dados:
        total = sum(quantidade for _, quantidade in dados)
        set_flash(request, f"Este clube tem {total} registos operacionais. Arquiva-o em vez de o eliminar.", "error")
        return RedirectResponse(f"/superadmin/clubes/{clube.id}/editar", status_code=303)

    nome = clube.nome_oficial
    _apagar_logo(clube.logo_principal)
    _apagar_logo(clube.logo_secundario)
    clube.administrador_principal_id = None
    db.flush()
    db.query(IdentidadeClube).execution_options(ignorar_clube=True).filter(
        IdentidadeClube.clube_id == clube.id
    ).delete(synchronize_session=False)
    db.query(Utilizador).execution_options(ignorar_clube=True).filter(
        Utilizador.clube_id == clube.id
    ).delete(synchronize_session=False)
    registar_auditoria(db, utilizador, "eliminar_clube", "clube", clube.id, f"Clube eliminado: {nome}", request)
    db.delete(clube)
    db.commit()
    if request.session.get("clube_suporte_id") == clube_id:
        request.session.pop("clube_suporte_id", None)
    set_flash(request, f"Clube '{nome}' eliminado.")
    return RedirectResponse("/superadmin/clubes", status_code=303)


@router.post("/clubes/novo")
async def criar_clube(
    request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_superadmin),
    nome_oficial: str = Form(...), nome_curto: str = Form(...), identificador: str = Form(""),
    cor_principal: str = Form("#f97316"), cor_secundaria: str = Form("#1f2937"),
    cor_destaque: str = Form("#0ea5e9"), epoca_inicial: str = Form(""),
    admin_nome: str = Form(...), admin_username: str = Form(...), admin_email: str = Form(...),
    admin_password: str = Form(...),
    logo_principal: UploadFile | None = File(None), logo_secundario: UploadFile | None = File(None),
):
    identificador = _slug(identificador or nome_curto)
    erro = None
    if not identificador:
        erro = "Indica um identificador válido."
    elif db.query(Clube).execution_options(ignorar_clube=True).filter(Clube.identificador == identificador).first():
        erro = "Já existe um clube com este identificador."
    elif db.query(Utilizador).execution_options(ignorar_clube=True).filter((Utilizador.username == admin_username) | (Utilizador.email == admin_email)).first():
        erro = "O username ou email do administrador já está em utilização."
    elif len(admin_password) < 8:
        erro = "A password inicial deve ter pelo menos 8 caracteres."
    if erro:
        return templates.TemplateResponse(request, "superadmin/clube_form.html", {"utilizador": utilizador, "erro": erro}, status_code=422)

    logos_guardados = []
    try:
        principal = normalizar_cor(cor_principal, "#f97316")
        clube = Clube(
            nome_oficial=nome_oficial.strip(), nome_curto=nome_curto.strip(), identificador=identificador,
            cor_principal=principal, cor_secundaria=normalizar_cor(cor_secundaria, "#1f2937"),
            cor_destaque=normalizar_cor(cor_destaque, "#0ea5e9"), epoca_inicial=epoca_inicial or None,
            estado=EstadoClubeEnum.ativo, tema_gerado=json.dumps({"principal": principal}),
        )
        db.add(clube)
        db.flush()
        clube.logo_principal = await _guardar_logo(logo_principal, f"clube-{clube.id}-logo-principal")
        if clube.logo_principal:
            logos_guardados.append(clube.logo_principal)
        clube.logo_secundario = await _guardar_logo(logo_secundario, f"clube-{clube.id}-logo-secundario")
        if clube.logo_secundario:
            logos_guardados.append(clube.logo_secundario)
        admin = Utilizador(
            nome=admin_nome.strip(), username=admin_username.strip(), email=admin_email.strip(),
            password_hash=encriptar_password(admin_password), perfil=PerfilEnum.administrador,
            ativo=True, clube_id=clube.id, deve_alterar_password=True,
        )
        db.add(admin)
        db.flush()
        clube.administrador_principal_id = admin.id
        db.add(IdentidadeClube(
            clube_id=clube.id, nome_oficial=clube.nome_oficial, nome_curto=clube.nome_curto,
            logo_principal=clube.logo_principal, logo_secundario=clube.logo_secundario,
            cor_principal=clube.cor_principal, cor_secundaria=clube.cor_secundaria,
            cor_destaque=clube.cor_destaque, epoca_predefinida=clube.epoca_inicial,
        ))
        registar_auditoria(db, utilizador, "criar_clube", "clube", clube.id, f"Clube {clube.identificador}", request)
        db.commit()
    except ValueError as exc:
        db.rollback()
        for logo in logos_guardados:
            _apagar_logo(logo)
        return templates.TemplateResponse(request, "superadmin/clube_form.html", {"utilizador": utilizador, "erro": str(exc)}, status_code=422)
    except Exception:
        db.rollback()
        for logo in logos_guardados:
            _apagar_logo(logo)
        logger.exception("Falha ao criar clube pelo superadministrador.")
        return templates.TemplateResponse(request, "superadmin/clube_form.html", {
            "utilizador": utilizador,
            "erro": "Não foi possível criar o clube. Tenta novamente; se o erro persistir, consulta os registos da plataforma.",
        }, status_code=500)
    set_flash(request, "Clube e administrador principal criados com sucesso.")
    return RedirectResponse("/superadmin/clubes", status_code=303)


@router.post("/clubes/{clube_id}/estado")
def alterar_estado(clube_id: int, request: Request, estado: str = Form(...), db: Session = Depends(get_db), utilizador=Depends(exigir_superadmin)):
    clube = db.query(Clube).execution_options(ignorar_clube=True).filter(Clube.id == clube_id).first()
    if clube and estado in {item.value for item in EstadoClubeEnum}:
        clube.estado = EstadoClubeEnum(estado)
        registar_auditoria(db, utilizador, "alterar_estado_clube", "clube", clube.id, estado, request)
        db.commit()
    return RedirectResponse("/superadmin/clubes", status_code=303)


@router.post("/clubes/{clube_id}/entrar")
def entrar_suporte(clube_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_superadmin)):
    clube = db.query(Clube).execution_options(ignorar_clube=True).filter(Clube.id == clube_id).first()
    if not clube:
        return RedirectResponse("/superadmin/clubes", status_code=303)
    request.session["clube_suporte_id"] = clube.id
    token = definir_clube_atual(clube.id)
    try:
        registar_auditoria(db, utilizador, "iniciar_suporte", "clube", clube.id, "Entrada explícita no contexto do clube", request)
        db.commit()
    finally:
        repor_clube_atual(token)
    return RedirectResponse("/dashboard", status_code=303)


@router.post("/sair-suporte")
def sair_suporte(request: Request, utilizador=Depends(exigir_superadmin)):
    request.session.pop("clube_suporte_id", None)
    return RedirectResponse("/superadmin/clubes", status_code=303)

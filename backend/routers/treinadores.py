from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from template_config import Jinja2Templates
from sqlalchemy.orm import Session, joinedload

from auth import encriptar_password, verificar_perfil
from auth_deps import AcessoNegado, exigir_autenticacao, exigir_coordenacao
from database import get_db
from flash import set_flash
from models.equipa import Equipa
from models.treinador import Treinador
from models.utilizador import PerfilEnum, Utilizador
from paths import TEMPLATES_DIR

router = APIRouter(prefix="/treinadores")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

FUNCOES_EQUIPE_TECNICA = (
    "Treinador Principal", "Adjunto", "Team manager", "Treinador",
    "Fisioterapeuta", "Médico", "Seccionista", "Roupeiro",
    "Secretaria", "Presidente", "Vice-Presidente",
)


def _normalizar_funcao(funcao: str | None) -> str:
    return funcao if funcao in FUNCOES_EQUIPE_TECNICA else "Treinador"


def _voltar_seguro(voltar: str | None, padrao: str) -> str:
    return voltar if voltar and voltar.startswith("/equipas/") and "//" not in voltar else padrao


def _perfil_login_para_funcao(funcao: str) -> PerfilEnum:
    if funcao == "Fisioterapeuta":
        return PerfilEnum.fisioterapeuta
    if funcao in {"Treinador", "Treinador Principal", "Adjunto"}:
        return PerfilEnum.treinador
    if funcao == "Secretaria":
        return PerfilEnum.secretaria
    return PerfilEnum.staff


def _pode_gerir_equipa_tecnica(utilizador, equipa_id: int | None, db: Session) -> bool:
    """Permite gestão apenas no contexto da equipa atribuída."""
    if not equipa_id:
        return verificar_perfil(utilizador, ["administrador", "coordenador"])
    if verificar_perfil(utilizador, ["administrador", "coordenador"]):
        return True
    if not verificar_perfil(utilizador, ["treinador", "staff"]):
        return False
    from auth import verificar_acesso_equipa
    return verificar_acesso_equipa(utilizador, equipa_id, db)


def _equipas_do_formulario(utilizador, equipa_contexto_id: int | None, db: Session):
    if equipa_contexto_id and not verificar_perfil(utilizador, ["administrador", "coordenador"]):
        return db.query(Equipa).filter(Equipa.id == equipa_contexto_id).all()
    return db.query(Equipa).all()


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
    equipa_preselecionada = request.query_params.get("equipa_id", "")
    equipa_contexto_id = int(equipa_preselecionada) if equipa_preselecionada.isdigit() else None
    if not _pode_gerir_equipa_tecnica(utilizador, equipa_contexto_id, db):
        raise AcessoNegado("/equipas")
    equipas = _equipas_do_formulario(utilizador, equipa_contexto_id, db)
    return templates.TemplateResponse(request, "treinadores/form.html", {
        "utilizador": utilizador,
        "equipas": equipas,
        "treinador": None,
        "erro": None,
        "funcoes": FUNCOES_EQUIPE_TECNICA,
        "funcao_preselecionada": _normalizar_funcao(request.query_params.get("funcao")),
        "equipa_preselecionada": equipa_contexto_id,
        "equipa_contexto_id": equipa_contexto_id,
        "voltar": _voltar_seguro(request.query_params.get("voltar"), "/treinadores"),
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
    funcao: str = Form("Treinador"),
    observacoes: str = Form(""),
    equipas_ids: list[int] = Form(default=[]),
    equipa_contexto_id: int | None = Form(None),
    login_username: str = Form(""),
    login_password: str = Form(""),
    voltar: str = Form(""),
):
    if not _pode_gerir_equipa_tecnica(utilizador, equipa_contexto_id, db):
        raise AcessoNegado("/equipas")
    if equipa_contexto_id and not verificar_perfil(utilizador, ["administrador", "coordenador"]):
        equipas_ids = [equipa_contexto_id]
    # Validar username/password se fornecidos
    if login_username or login_password:
        if not login_username or not login_password:
            equipas = _equipas_do_formulario(utilizador, equipa_contexto_id, db)
            return templates.TemplateResponse(request, "treinadores/form.html", {
                "utilizador": utilizador,
                "equipas": equipas,
                "treinador": None,
                "erro": "Preenche o username e a password para criar o login.",
                "funcoes": FUNCOES_EQUIPE_TECNICA,
                "funcao_preselecionada": _normalizar_funcao(funcao),
                "equipa_preselecionada": None,
                "equipa_contexto_id": equipa_contexto_id,
                "voltar": _voltar_seguro(voltar, "/treinadores"),
            })
        if len(login_password) < 8:
            equipas = _equipas_do_formulario(utilizador, equipa_contexto_id, db)
            return templates.TemplateResponse(request, "treinadores/form.html", {
                "utilizador": utilizador,
                "equipas": equipas,
                "treinador": None,
                "erro": "A password deve ter pelo menos 8 caracteres.",
                "funcoes": FUNCOES_EQUIPE_TECNICA,
                "funcao_preselecionada": _normalizar_funcao(funcao),
                "equipa_preselecionada": None,
                "equipa_contexto_id": equipa_contexto_id,
                "voltar": _voltar_seguro(voltar, "/treinadores"),
            })
        if db.query(Utilizador).filter(Utilizador.username == login_username).first():
            equipas = _equipas_do_formulario(utilizador, equipa_contexto_id, db)
            return templates.TemplateResponse(request, "treinadores/form.html", {
                "utilizador": utilizador,
                "equipas": equipas,
                "treinador": None,
                "erro": f"O username '{login_username}' já está em uso.",
                "funcoes": FUNCOES_EQUIPE_TECNICA,
                "funcao_preselecionada": _normalizar_funcao(funcao),
                "equipa_preselecionada": None,
                "equipa_contexto_id": equipa_contexto_id,
                "voltar": _voltar_seguro(voltar, "/treinadores"),
            })

    funcao_normalizada = _normalizar_funcao(funcao)
    treinador = Treinador(
        nome=nome,
        data_nascimento=date.fromisoformat(data_nascimento) if data_nascimento else None,
        morada=morada or None,
        telefone=telefone or None,
        email=email or None,
        numero_cedula=numero_cedula or None,
        numero_fpb=numero_fpb or None,
        funcao=funcao_normalizada,
        observacoes=observacoes or None,
    )

    if equipas_ids:
        treinador.equipas = db.query(Equipa).filter(Equipa.id.in_(equipas_ids)).all()

    db.add(treinador)
    db.flush()  # gera o treinador.id sem fechar a transação

    if login_username and login_password:
        conta = Utilizador(
            nome=nome,
            username=login_username,
            email=email or f"{login_username}@treinador.local",
            password_hash=encriptar_password(login_password),
            perfil=_perfil_login_para_funcao(funcao_normalizada),
            treinador_id=treinador.id,
        )
        if conta.perfil in {PerfilEnum.staff, PerfilEnum.fisioterapeuta}:
            conta.equipas_staff = list(treinador.equipas)
        db.add(conta)

    db.commit()
    set_flash(request, f"{funcao_normalizada} '{nome}' criado(a) com sucesso.")
    return RedirectResponse(url=_voltar_seguro(voltar, "/treinadores"), status_code=303)


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
    utilizador=Depends(exigir_autenticacao),
):
    treinador = db.query(Treinador).filter(Treinador.id == treinador_id).first()
    if not treinador:
        return RedirectResponse(url="/treinadores")

    equipa_parametro = request.query_params.get("equipa_id", "")
    equipa_contexto_id = int(equipa_parametro) if equipa_parametro.isdigit() else None
    if not _pode_gerir_equipa_tecnica(utilizador, equipa_contexto_id, db):
        raise AcessoNegado("/equipas")
    if equipa_contexto_id:
        equipa_contexto = db.query(Equipa).filter(Equipa.id == equipa_contexto_id).first()
        if not equipa_contexto or treinador not in equipa_contexto.treinadores:
            raise AcessoNegado(f"/equipas/{equipa_contexto_id}/equipa-tecnica")
    equipas = _equipas_do_formulario(utilizador, equipa_contexto_id, db)
    return templates.TemplateResponse(request, "treinadores/form.html", {
        "utilizador": utilizador,
        "treinador": treinador,
        "equipas": equipas,
        "funcoes": FUNCOES_EQUIPE_TECNICA,
        "funcao_preselecionada": treinador.funcao,
        "equipa_preselecionada": None,
        "equipa_contexto_id": equipa_contexto_id,
        "voltar": _voltar_seguro(request.query_params.get("voltar"), f"/treinadores/{treinador_id}"),
    })


@router.post("/{treinador_id}/editar")
async def editar_treinador(
    treinador_id: int,
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
    funcao: str = Form("Treinador"),
    observacoes: str = Form(""),
    equipas_ids: list[int] = Form(default=[]),
    equipa_contexto_id: int | None = Form(None),
    voltar: str = Form(""),
):
    treinador = db.query(Treinador).filter(Treinador.id == treinador_id).first()
    if not treinador:
        return RedirectResponse(url="/treinadores")
    if not _pode_gerir_equipa_tecnica(utilizador, equipa_contexto_id, db):
        raise AcessoNegado("/equipas")
    if equipa_contexto_id and not verificar_perfil(utilizador, ["administrador", "coordenador"]):
        equipa_contexto = db.query(Equipa).filter(Equipa.id == equipa_contexto_id).first()
        if not equipa_contexto or treinador not in equipa_contexto.treinadores:
            raise AcessoNegado(f"/equipas/{equipa_contexto_id}/equipa-tecnica")
        equipas_ids = [equipa.id for equipa in treinador.equipas]

    treinador.nome = nome
    treinador.data_nascimento = date.fromisoformat(data_nascimento) if data_nascimento else None
    treinador.morada = morada or None
    treinador.telefone = telefone or None
    treinador.email = email or None
    treinador.numero_cedula = numero_cedula or None
    treinador.numero_fpb = numero_fpb or None
    treinador.funcao = _normalizar_funcao(funcao)
    treinador.observacoes = observacoes or None
    treinador.equipas = db.query(Equipa).filter(Equipa.id.in_(equipas_ids)).all() if equipas_ids else []

    db.commit()
    set_flash(request, f"Treinador '{nome}' atualizado com sucesso.")
    return RedirectResponse(url=_voltar_seguro(voltar, f"/treinadores/{treinador_id}"), status_code=303)


@router.post("/{treinador_id}/apagar")
def apagar_treinador(
    treinador_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_coordenacao),
):
    treinador = db.query(Treinador).filter(Treinador.id == treinador_id).first()
    if treinador:
        nome = treinador.nome
        db.delete(treinador)
        db.commit()
        set_flash(request, f"Treinador '{nome}' apagado.")

    return RedirectResponse(url="/treinadores", status_code=303)

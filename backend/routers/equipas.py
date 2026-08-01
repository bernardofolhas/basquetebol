from datetime import date, timedelta

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from template_config import Jinja2Templates
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from auth import verificar_perfil
from auth_deps import (
    AcessoNegado,
    exigir_admin,
    exigir_autenticacao,
    exigir_coordenacao,
    exigir_operacao_desportiva,
    verificar_ou_negar_equipa,
)
from database import get_db
from flash import set_flash
from models.atribuicao_espaco_semanal import AtribuicaoEspacoSemanal
from models.equipa import Equipa, EscalaoEnum, GeneroEnum
from models.fisico import PlaneamentoFisico
from models.jogo import Jogo
from models.planeamento import Macrociclo
from models.planeamento_clube import EventoPlaneamentoClube
from models.playbook import Playbook
from paths import TEMPLATES_DIR
from services.planeamento_integrado_service import obter_dashboard_planeamento_equipa

router = APIRouter(prefix="/equipas")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _ordenar_jogadores(jogadores):
    return sorted(
        jogadores,
        key=lambda jogador: (
            jogador.numero_camisola is None,
            jogador.numero_camisola if jogador.numero_camisola is not None else 999,
            (jogador.nome or "").lower(),
        ),
    )


def _ordenar_treinadores(treinadores):
    return sorted(
        treinadores,
        key=lambda treinador: ((treinador.nome or "").lower(), treinador.id),
    )


def _carregar_equipa_detalhe(equipa_id: int, db: Session):
    equipa = db.query(Equipa).options(
        joinedload(Equipa.jogadores)
    ).filter(Equipa.id == equipa_id).first()
    if not equipa:
        return None

    equipa.jogadores = _ordenar_jogadores(list(equipa.jogadores))
    equipa.treinadores = _ordenar_treinadores(list(equipa.treinadores))
    return equipa


def _eventos_visiveis_equipa(equipa_id: int, db: Session):
    eventos_globais = db.query(EventoPlaneamentoClube).order_by(
        EventoPlaneamentoClube.data.asc(),
        EventoPlaneamentoClube.hora_inicio.asc(),
    ).all()
    return [
        evento for evento in eventos_globais
        if evento.aplica_a_todas_equipas
        or evento.equipa_id == equipa_id
        or any(item.id == equipa_id for item in evento.equipas)
    ]


@router.get("", response_class=HTMLResponse)
def listar_equipas(
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_operacao_desportiva),
):
    from auth import verificar_perfil
    if verificar_perfil(utilizador, ["administrador", "coordenador"]):
        equipas = db.query(Equipa).options(joinedload(Equipa.jogadores)).all()
    else:
        if utilizador.treinador_id:
            from models.treinador import Treinador
            treinador = db.query(Treinador).options(
                joinedload(Treinador.equipas)
            ).filter(Treinador.id == utilizador.treinador_id).first()
            equipas = treinador.equipas if treinador else []
        else:
            equipas = []

    return templates.TemplateResponse(request, "equipas/lista.html", {
        "utilizador": utilizador,
        "equipas": equipas,
    })


@router.get("/nova", response_class=HTMLResponse)
def form_nova_equipa(
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_coordenacao),
):
    return templates.TemplateResponse(request, "equipas/form.html", {
        "utilizador": utilizador,
        "escaloes": EscalaoEnum,
        "generos": GeneroEnum,
        "equipa": None,
    })


@router.post("/nova")
async def criar_equipa(
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_coordenacao),
    nome: str = Form(...),
    escalao: str = Form(...),
    genero: str = Form(...),
    seccionista: str = Form(""),
):
    equipa = Equipa(
        nome=nome,
        escalao=escalao,
        genero=genero,
        seccionista=seccionista or None,
    )
    db.add(equipa)
    db.commit()
    set_flash(request, f"Equipa '{nome}' criada com sucesso.")
    return RedirectResponse(url="/equipas", status_code=303)


@router.get("/{equipa_id}", response_class=HTMLResponse)
def detalhe_equipa(
    equipa_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    verificar_ou_negar_equipa(utilizador, equipa_id, db)

    equipa = _carregar_equipa_detalhe(equipa_id, db)
    if not equipa:
        return RedirectResponse(url="/equipas")

    hoje = date.today()
    agenda = obter_dashboard_planeamento_equipa(
        db,
        equipa_id,
        hoje,
        hoje + timedelta(days=14),
    )["itens"]

    return templates.TemplateResponse(request, "equipas/detalhe.html", {
        "utilizador": utilizador,
        "equipa": equipa,
        "agenda_proxima": agenda,
        "erro": None,
    })


@router.get("/{equipa_id}/equipa-tecnica", response_class=HTMLResponse)
def equipa_tecnica_equipa(
    equipa_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    verificar_ou_negar_equipa(utilizador, equipa_id, db)

    equipa = _carregar_equipa_detalhe(equipa_id, db)
    if not equipa:
        return RedirectResponse(url="/equipas")

    return templates.TemplateResponse(request, "equipas/equipa_tecnica.html", {
        "utilizador": utilizador,
        "equipa": equipa,
    })


@router.get("/{equipa_id}/eventos", response_class=HTMLResponse)
def eventos_equipa(
    equipa_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    verificar_ou_negar_equipa(utilizador, equipa_id, db)

    equipa = _carregar_equipa_detalhe(equipa_id, db)
    if not equipa:
        return RedirectResponse(url="/equipas")

    return templates.TemplateResponse(request, "equipas/eventos.html", {
        "utilizador": utilizador,
        "equipa": equipa,
        "eventos_globais": _eventos_visiveis_equipa(equipa_id, db),
    })


@router.get("/{equipa_id}/plantel", response_class=HTMLResponse)
def plantel_equipa(
    equipa_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    verificar_ou_negar_equipa(utilizador, equipa_id, db)

    equipa = _carregar_equipa_detalhe(equipa_id, db)
    if not equipa:
        return RedirectResponse(url="/equipas")
    for jogador in equipa.jogadores:
        registos = sorted(jogador.registos_antropometricos or [], key=lambda item: item.data, reverse=True)
        jogador.altura_atual = registos[0].altura if registos else None

    return templates.TemplateResponse(request, "equipas/plantel.html", {
        "utilizador": utilizador,
        "equipa": equipa,
    })


@router.get("/{equipa_id}/editar", response_class=HTMLResponse)
def form_editar_equipa(
    equipa_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_coordenacao),
):
    verificar_ou_negar_equipa(utilizador, equipa_id, db)

    equipa = db.query(Equipa).filter(Equipa.id == equipa_id).first()
    if not equipa:
        return RedirectResponse(url="/equipas")

    return templates.TemplateResponse(request, "equipas/form.html", {
        "utilizador": utilizador,
        "escaloes": EscalaoEnum,
        "generos": GeneroEnum,
        "equipa": equipa,
    })


@router.post("/{equipa_id}/editar")
async def editar_equipa(
    equipa_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_coordenacao),
    nome: str = Form(...),
    escalao: str = Form(...),
    genero: str = Form(...),
    seccionista: str = Form(""),
):
    verificar_ou_negar_equipa(utilizador, equipa_id, db)

    equipa = db.query(Equipa).filter(Equipa.id == equipa_id).first()
    if not equipa:
        return RedirectResponse(url="/equipas")

    equipa.nome = nome
    equipa.escalao = escalao
    equipa.genero = genero
    equipa.seccionista = seccionista or None

    db.commit()
    set_flash(request, f"Equipa '{nome}' atualizada com sucesso.")
    return RedirectResponse(url=f"/equipas/{equipa_id}", status_code=303)


@router.post("/{equipa_id}/apagar")
def apagar_equipa(
    equipa_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_admin),
):
    equipa = db.query(Equipa).filter(Equipa.id == equipa_id).first()
    if not equipa:
        return RedirectResponse(url="/equipas", status_code=303)

    nome = equipa.nome

    for atribuicao in db.query(AtribuicaoEspacoSemanal).filter(
        AtribuicaoEspacoSemanal.equipa_id == equipa_id
    ).all():
        atribuicao.equipa_id = None

    for evento in db.query(EventoPlaneamentoClube).filter(
        or_(
            EventoPlaneamentoClube.equipa_id == equipa_id,
            EventoPlaneamentoClube.equipas.any(Equipa.id == equipa_id),
        )
    ).all():
        if evento.equipa_id == equipa_id:
            evento.equipa_id = None
        evento.equipas = [item for item in evento.equipas if item.id != equipa_id]

    for jogo in db.query(Jogo).filter(Jogo.equipa_id == equipa_id).all():
        db.delete(jogo)

    for pf in db.query(PlaneamentoFisico).filter(PlaneamentoFisico.equipa_id == equipa_id).all():
        db.delete(pf)

    for macro in db.query(Macrociclo).filter(Macrociclo.equipa_id == equipa_id).all():
        db.delete(macro)

    # O playbook pertence exclusivamente à equipa. Removê-lo explicitamente
    # evita que o SQLAlchemy tente anular um FK obrigatório antes da equipa.
    for playbook in db.query(Playbook).filter(Playbook.equipa_id == equipa_id).all():
        db.delete(playbook)

    db.delete(equipa)
    db.commit()
    set_flash(request, f"Equipa '{nome}' apagada.")

    return RedirectResponse(url="/equipas", status_code=303)

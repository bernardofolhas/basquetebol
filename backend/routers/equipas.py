from datetime import date, timedelta

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from template_config import Jinja2Templates
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from auth import verificar_perfil
from auth_deps import (
    AcessoNegado,
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
from models.treinador import Treinador
from models.utilizador import PerfilEnum, Utilizador
from paths import TEMPLATES_DIR
from services.desenho_service import imagem_estatica_data_uri
from services.fotografia_jogador_service import caminho_fotografia
from services.pdf_service import content_disposition_pdf, renderizar_pdf
from services.planeamento_integrado_service import obter_dashboard_planeamento_equipa
from services.planeamento_semanal_administrativo_service import obter_previsao_equipa

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


FUNCOES_EQUIPE_TECNICA = (
    "Treinador Principal", "Adjunto", "Team manager", "Treinador",
    "Fisioterapeuta", "Médico", "Seccionista", "Roupeiro",
    "Secretaria", "Presidente", "Vice-Presidente",
)


def _agrupar_equipa_tecnica(elementos):
    grupos = {}
    for elemento in elementos:
        funcao = (elemento.funcao or "Treinador").strip() or "Treinador"
        if funcao.casefold() in {"treinador", "treinador principal"}:
            funcao = "Treinador Principal"
        elif funcao.casefold() in {"adjunto", "treinador adjunto"}:
            funcao = "Adjunto"
        elif funcao.casefold() == "team manager":
            funcao = "Team manager"
        grupos.setdefault(funcao, []).append(elemento)
    prioritarias = ("Treinador Principal", "Adjunto", "Team manager")
    restantes = sorted((funcao for funcao in grupos if funcao not in prioritarias), key=str.casefold)
    titulos = {
        "Treinador Principal": "Treinador principal",
        "Adjunto": "Treinadores adjuntos",
        "Team manager": "Team managers",
        "Fisioterapeuta": "Fisioterapeutas",
        "Médico": "Médicos",
        "Seccionista": "Seccionistas",
        "Roupeiro": "Roupeiros",
        "Presidente": "Presidentes",
        "Vice-Presidente": "Vice-presidentes",
    }
    return [
        (titulos.get(funcao, funcao), _ordenar_treinadores(grupos[funcao]))
        for funcao in (*prioritarias, *restantes) if funcao in grupos
    ]


def _pode_gerir_equipa(utilizador) -> bool:
    return verificar_perfil(utilizador, ["administrador", "coordenador", "treinador", "staff"])


def _sincronizar_utilizadores_tecnicos(db: Session) -> None:
    """Expõe contas técnicas já existentes como elementos selecionáveis."""
    contas = db.query(Utilizador).filter(
        Utilizador.perfil.in_([PerfilEnum.staff, PerfilEnum.fisioterapeuta, PerfilEnum.secretaria])
    ).all()
    alterado = False
    for conta in contas:
        funcao_por_perfil = {
            PerfilEnum.fisioterapeuta: "Fisioterapeuta",
            PerfilEnum.secretaria: "Secretaria",
            PerfilEnum.staff: "Seccionista",
        }
        funcao = funcao_por_perfil[conta.perfil]
        elemento = conta.treinador
        if elemento is None:
            elemento = Treinador(
                clube_id=conta.clube_id,
                nome=conta.nome,
                email=conta.email,
                funcao=funcao,
            )
            db.add(elemento)
            db.flush()
            conta.treinador_id = elemento.id
            alterado = True
        if conta.perfil in {PerfilEnum.fisioterapeuta, PerfilEnum.secretaria} and elemento.funcao != funcao:
            elemento.funcao = funcao
            alterado = True
        # Instalações anteriores podem ter gravado a associação apenas no
        # elemento técnico. Mantemos os dois lados sincronizados.
        equipas_associadas = {equipa.id: equipa for equipa in conta.equipas_staff}
        for equipa in elemento.equipas:
            equipas_associadas.setdefault(equipa.id, equipa)
        for equipa in equipas_associadas.values():
            if equipa not in elemento.equipas:
                elemento.equipas.append(equipa)
                alterado = True
            if equipa not in conta.equipas_staff:
                conta.equipas_staff.append(equipa)
                alterado = True
    if alterado:
        db.commit()


def _calcular_idade(data_nascimento: date | None, hoje: date | None = None) -> int | None:
    if not data_nascimento:
        return None
    referencia = hoje or date.today()
    return referencia.year - data_nascimento.year - (
        (referencia.month, referencia.day) < (data_nascimento.month, data_nascimento.day)
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
    eventos_globais = db.query(EventoPlaneamentoClube).filter(
        EventoPlaneamentoClube.ativo.is_(True),
    ).order_by(
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
    elif getattr(utilizador.perfil, "value", utilizador.perfil) in {"staff", "fisioterapeuta"}:
        equipas = list(utilizador.equipas_staff or [])
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
def abrir_equipa(
    equipa_id: int,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    verificar_ou_negar_equipa(utilizador, equipa_id, db)
    return RedirectResponse(url=f"/equipas/{equipa_id}/resumo", status_code=303)


@router.get("/{equipa_id}/resumo", response_class=HTMLResponse)
def detalhe_equipa(
    equipa_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    verificar_ou_negar_equipa(utilizador, equipa_id, db)
    _sincronizar_utilizadores_tecnicos(db)

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
    inicio_semana = hoje - timedelta(days=hoje.weekday())
    semana_prevista = obter_previsao_equipa(
        db, equipa_id, inicio_semana, inicio_semana + timedelta(days=6)
    )

    template = "equipas/resumo_fisioterapeuta.html" if utilizador.perfil.value == "fisioterapeuta" else "equipas/detalhe.html"
    contexto = {
        "utilizador": utilizador,
        "equipa": equipa,
        "agenda_proxima": agenda,
        "semana_prevista": semana_prevista,
        "erro": None,
    }
    if utilizador.perfil.value == "fisioterapeuta":
        from services.dashboard_service import obter_resumo_fisioterapia
        contexto["dados_fisioterapia"] = obter_resumo_fisioterapia(db, equipa)
    return templates.TemplateResponse(request, template, contexto)


@router.get("/{equipa_id}/equipa-tecnica", response_class=HTMLResponse)
def equipa_tecnica_equipa(
    equipa_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    verificar_ou_negar_equipa(utilizador, equipa_id, db)

    _sincronizar_utilizadores_tecnicos(db)

    equipa = _carregar_equipa_detalhe(equipa_id, db)
    if not equipa:
        return RedirectResponse(url="/equipas")

    return templates.TemplateResponse(request, "equipas/equipa_tecnica.html", {
        "utilizador": utilizador,
        "equipa": equipa,
        "secoes_tecnicas": _agrupar_equipa_tecnica(equipa.treinadores),
        "funcoes_tecnicas": FUNCOES_EQUIPE_TECNICA,
        "pode_gerir_equipa_tecnica": verificar_perfil(
            utilizador, ["administrador", "coordenador", "treinador", "staff"]
        ),
        "elementos_disponiveis": _ordenar_treinadores(
            db.query(Treinador).filter(~Treinador.equipas.any(Equipa.id == equipa_id)).all()
        ),
    })


@router.post("/{equipa_id}/equipa-tecnica/associar")
def associar_elemento_equipa_tecnica(
    equipa_id: int,
    request: Request,
    elemento_id: int = Form(...),
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_operacao_desportiva),
):
    verificar_ou_negar_equipa(utilizador, equipa_id, db)
    if not _pode_gerir_equipa(utilizador):
        raise AcessoNegado(f"/equipas/{equipa_id}/equipa-tecnica")
    equipa = db.query(Equipa).filter(Equipa.id == equipa_id).first()
    elemento = db.query(Treinador).filter(Treinador.id == elemento_id).first()
    if not equipa or not elemento:
        set_flash(request, "Não foi possível associar o elemento selecionado.", "error")
    elif elemento not in equipa.treinadores:
        equipa.treinadores.append(elemento)
        db.commit()
        set_flash(request, f"{elemento.nome} associado(a) à equipa.")
    return RedirectResponse(url=f"/equipas/{equipa_id}/equipa-tecnica", status_code=303)


@router.post("/{equipa_id}/equipa-tecnica/{elemento_id}/desassociar")
def desassociar_elemento_equipa_tecnica(
    equipa_id: int,
    elemento_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_operacao_desportiva),
):
    verificar_ou_negar_equipa(utilizador, equipa_id, db)
    if not _pode_gerir_equipa(utilizador):
        raise AcessoNegado(f"/equipas/{equipa_id}/equipa-tecnica")
    equipa = db.query(Equipa).filter(Equipa.id == equipa_id).first()
    elemento = db.query(Treinador).filter(Treinador.id == elemento_id).first()
    if equipa and elemento and elemento in equipa.treinadores:
        equipa.treinadores.remove(elemento)
        db.commit()
        set_flash(request, f"{elemento.nome} deixou de estar associado(a) a esta equipa.")
    return RedirectResponse(url=f"/equipas/{equipa_id}/equipa-tecnica", status_code=303)


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


@router.get("/{equipa_id}/plantel/pdf")
def exportar_pdf_plantel(
    equipa_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    verificar_ou_negar_equipa(utilizador, equipa_id, db)

    equipa = _carregar_equipa_detalhe(equipa_id, db)
    if not equipa:
        return RedirectResponse(url="/equipas", status_code=303)

    atletas = []
    idades = []
    for jogador in equipa.jogadores:
        if not jogador.ativo:
            continue
        idade = _calcular_idade(jogador.data_nascimento)
        if idade is not None:
            idades.append(idade)
        registos = sorted(
            jogador.registos_antropometricos or [],
            key=lambda item: item.data,
            reverse=True,
        )
        caminho_foto = caminho_fotografia(jogador.fotografia)
        atletas.append({
            "jogador": jogador,
            "idade": idade,
            "altura": registos[0].altura if registos else None,
            "fotografia": imagem_estatica_data_uri(caminho_foto, "image/jpeg") if caminho_foto else None,
        })

    nome_treinador = equipa.treinadores[0].nome if equipa.treinadores else utilizador.nome
    pdf = renderizar_pdf(request, "equipas/plantel_pdf.html", {
        "utilizador": utilizador,
        "equipa": equipa,
        "atletas": atletas,
        "media_idades": round(sum(idades) / len(idades), 1) if idades else None,
        "idades_registadas": len(idades),
        "nome_treinador": nome_treinador,
    })
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": content_disposition_pdf(f"Plantel {equipa.nome}")},
    )


@router.get("/{equipa_id}/editar", response_class=HTMLResponse)
def form_editar_equipa(
    equipa_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_operacao_desportiva),
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
    utilizador=Depends(exigir_operacao_desportiva),
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
    return RedirectResponse(url=f"/equipas/{equipa_id}/resumo", status_code=303)


@router.post("/{equipa_id}/apagar")
def apagar_equipa(
    equipa_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_coordenacao),
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

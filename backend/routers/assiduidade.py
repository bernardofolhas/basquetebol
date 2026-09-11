from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from template_config import Jinja2Templates
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from auth_deps import AcessoNegado, exigir_autenticacao, verificar_ou_negar_equipa
from database import get_db
from flash import set_flash
from models.assiduidade import ConvocacaoAssiduidade, RegistoAssiduidade
from models.equipa import Equipa
from models.jogador import Jogador
from models.planeamento import Macrociclo, Mesociclo, Microciclo, SessaoTreino
from paths import TEMPLATES_DIR
from services.sincronizacao_ui import enriquecer_sessao_para_ui
from services.pdf_service import renderizar_pdf
from services.assiduidade_service import (
    ESTADOS_ASSIDUIDADE,
    ESTADOS_ASSIDUIDADE_VISUAL,
    calcular_resumo_assiduidade,
    estado_assiduidade_visual,
    estado_para_presenca,
    normalizar_estado_assiduidade,
    obter_relatorio_assiduidade_equipa,
)
from services.sessao_workflow import normalizar_estado_sessao

router = APIRouter(prefix="/assiduidade")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _data_query(valor: str | None) -> date | None:
    try:
        return date.fromisoformat(valor) if valor else None
    except ValueError:
        return None


def _normalizar_rpe_individual(valor: str | None) -> float | None:
    texto = (valor or "").strip().replace(",", ".")
    if not texto:
        return None
    try:
        rpe = float(texto)
    except ValueError:
        raise ValueError("O RPE individual deve ser um número entre 0 e 10.") from None
    if not 0 <= rpe <= 10:
        raise ValueError("O RPE individual deve estar entre 0 e 10.")
    return rpe


def _contexto_relatorio_equipa(request: Request, equipa, relatorio: dict, utilizador) -> dict:
    return {
        "utilizador": utilizador,
        "equipa": equipa,
        **relatorio,
        "estados_assiduidade": ESTADOS_ASSIDUIDADE,
        "estados_assiduidade_visual": ESTADOS_ASSIDUIDADE_VISUAL,
        "request": request,
    }


def _sessoes_assiduidade_equipa(db: Session, equipa_id: int):
    return (
        db.query(SessaoTreino)
        .join(Microciclo, SessaoTreino.microciclo_id == Microciclo.id)
        .join(Mesociclo, Microciclo.mesociclo_id == Mesociclo.id)
        .join(Macrociclo, Mesociclo.macrociclo_id == Macrociclo.id)
        .filter(
            Macrociclo.equipa_id == equipa_id,
            SessaoTreino.ativa.is_(True),
        )
        .order_by(SessaoTreino.data.desc(), SessaoTreino.hora_inicio.desc())
        .limit(100)
        .all()
    )


def _jogadores_folha_assiduidade(db: Session, equipa, sessao_id: int):
    """Devolve o plantel da equipa mais os convocados apenas para esta sessão."""
    plantel = db.query(Jogador).filter(
        Jogador.equipa_id == equipa.id,
        Jogador.ativo.is_(True),
    ).order_by(Jogador.nome).all()
    convocados = (
        db.query(Jogador)
        .join(ConvocacaoAssiduidade, ConvocacaoAssiduidade.jogador_id == Jogador.id)
        .filter(
            ConvocacaoAssiduidade.sessao_id == sessao_id,
            ConvocacaoAssiduidade.clube_id == equipa.clube_id,
            Jogador.ativo.is_(True),
        )
        .order_by(Jogador.nome)
        .all()
    )
    ids_plantel = {jogador.id for jogador in plantel}
    return plantel + [jogador for jogador in convocados if jogador.id not in ids_plantel], convocados


def _jogadores_disponiveis_para_convocatoria(db: Session, equipa, sessao_id: int):
    convocados_ids = db.query(ConvocacaoAssiduidade.jogador_id).filter(
        ConvocacaoAssiduidade.sessao_id == sessao_id,
        ConvocacaoAssiduidade.clube_id == equipa.clube_id,
    )
    return (
        db.query(Jogador)
        .filter(
            Jogador.clube_id == equipa.clube_id,
            Jogador.ativo.is_(True),
            or_(Jogador.equipa_id.is_(None), Jogador.equipa_id != equipa.id),
            ~Jogador.id.in_(convocados_ids),
        )
        .order_by(Jogador.nome)
        .all()
    )


@router.get("/equipas/{equipa_id}/registar")
def abrir_folha_assiduidade_equipa(
    equipa_id: int,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    verificar_ou_negar_equipa(utilizador, equipa_id, db)
    sessoes = _sessoes_assiduidade_equipa(db, equipa_id)
    hoje = date.today()
    sessao = next((item for item in sessoes if item.data <= hoje), None)
    if not sessao and sessoes:
        sessao = min(sessoes, key=lambda item: (item.data, item.hora_inicio or ""))
    destino = f"/assiduidade/sessoes/{sessao.id}" if sessao else f"/assiduidade/equipas/{equipa_id}"
    return RedirectResponse(url=destino, status_code=303)


def _sessoes_do_dia(db: Session, equipa_id: int, dia: date):
    """Obtém apenas treinos activos da equipa na data indicada."""
    return (
        db.query(SessaoTreino)
        .join(Microciclo, SessaoTreino.microciclo_id == Microciclo.id)
        .join(Mesociclo, Microciclo.mesociclo_id == Mesociclo.id)
        .join(Macrociclo, Mesociclo.macrociclo_id == Macrociclo.id)
        .filter(
            Macrociclo.equipa_id == equipa_id,
            SessaoTreino.data == dia,
            SessaoTreino.e_jogo.is_(False),
            SessaoTreino.ativa.is_(True),
        )
        .order_by(SessaoTreino.hora_inicio.asc(), SessaoTreino.id.asc())
        .all()
    )


@router.get("/equipas/{equipa_id}/pse", response_class=HTMLResponse)
def pagina_pse_individual(
    equipa_id: int,
    request: Request,
    sessao_id: int | None = None,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    """Abre o preenchimento rápido da PSE para o treino de hoje."""
    verificar_ou_negar_equipa(utilizador, equipa_id, db)
    equipa = db.query(Equipa).filter(Equipa.id == equipa_id).first()
    if not equipa:
        return RedirectResponse(url="/dashboard", status_code=303)

    sessoes_hoje = _sessoes_do_dia(db, equipa_id, date.today())
    sessao = next((item for item in sessoes_hoje if item.id == sessao_id), None) if sessao_id else None
    if sessao is None and sessoes_hoje:
        sessao = sessoes_hoje[0]

    jogadores = []
    registos_dict = {}
    total_preenchidos = 0
    if sessao:
        jogadores, _ = _jogadores_folha_assiduidade(db, equipa, sessao.id)
        registos = db.query(RegistoAssiduidade).filter(
            RegistoAssiduidade.sessao_id == sessao.id,
        ).all()
        registos_dict = {registo.jogador_id: registo for registo in registos}
        total_preenchidos = sum(
            1 for registo in registos if registo.rpe_individual is not None
        )

    return templates.TemplateResponse(request, "assiduidade/pse_individual.html", {
        "utilizador": utilizador,
        "equipa": equipa,
        "sessao": sessao,
        "sessoes_hoje": sessoes_hoje,
        "jogadores": jogadores,
        "registos_dict": registos_dict,
        "total_preenchidos": total_preenchidos,
        "data_hoje": date.today(),
    })


@router.post("/sessoes/{sessao_id}/pse")
async def guardar_pse_individual(
    sessao_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    """Guarda apenas as PSE preenchidas na folha rápida do staff."""
    sessao = db.query(SessaoTreino).filter(SessaoTreino.id == sessao_id).first()
    if not sessao:
        return RedirectResponse(url="/dashboard", status_code=303)
    equipa = sessao.microciclo.mesociclo.macrociclo.equipa
    verificar_ou_negar_equipa(utilizador, equipa.id, db)

    dados = await request.form()
    jogadores, _ = _jogadores_folha_assiduidade(db, equipa, sessao_id)
    registos = db.query(RegistoAssiduidade).filter(
        RegistoAssiduidade.sessao_id == sessao_id,
    ).all()
    registos_por_jogador = {registo.jogador_id: registo for registo in registos}

    try:
        valores = []
        for jogador in jogadores:
            campo = f"rpe_{jogador.id}"
            if campo not in dados:
                continue
            valor = dados.get(campo)
            rpe = _normalizar_rpe_individual(valor) if str(valor or "").strip() else None
            valores.append((jogador, rpe))
    except ValueError as erro:
        set_flash(request, str(erro), "error")
        return RedirectResponse(url=f"/assiduidade/equipas/{equipa.id}/pse", status_code=303)

    for jogador, rpe in valores:
        registo = registos_por_jogador.get(jogador.id)
        if not registo and rpe is not None:
            registo = RegistoAssiduidade(
                sessao_id=sessao_id,
                jogador_id=jogador.id,
                clube_id=equipa.clube_id,
                presente=True,
                estado="presente",
            )
            db.add(registo)
        if registo:
            registo.rpe_individual = rpe
            if rpe is not None:
                registo.presente = True
                registo.estado = "presente"

    db.commit()
    set_flash(request, "PSE individual guardada com sucesso.")
    return RedirectResponse(url=f"/assiduidade/equipas/{equipa.id}/pse?sessao_id={sessao_id}", status_code=303)


@router.get("/equipas/{equipa_id}", response_class=HTMLResponse)
def relatorio_assiduidade_equipa(
    equipa_id: int,
    request: Request,
    inicio: str = "",
    fim: str = "",
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    verificar_ou_negar_equipa(utilizador, equipa_id, db)
    equipa = db.query(Equipa).filter(Equipa.id == equipa_id).first()
    if not equipa:
        return RedirectResponse(url="/equipas")

    relatorio = obter_relatorio_assiduidade_equipa(
        db,
        equipa_id,
        _data_query(inicio),
        _data_query(fim),
    )
    total_jogadores_ativos = db.query(Jogador).filter(
        Jogador.equipa_id == equipa_id,
        Jogador.ativo.is_(True),
    ).count()
    sessoes = relatorio["sessoes"]
    sessoes_ids = [sessao.id for sessao in sessoes]
    contagens = dict(
        db.query(RegistoAssiduidade.sessao_id, func.count(RegistoAssiduidade.id))
        .filter(RegistoAssiduidade.sessao_id.in_(sessoes_ids))
        .group_by(RegistoAssiduidade.sessao_id)
        .all()
    ) if sessoes_ids else {}
    convocacoes_por_sessao = dict(
        db.query(ConvocacaoAssiduidade.sessao_id, func.count(ConvocacaoAssiduidade.id))
        .filter(ConvocacaoAssiduidade.sessao_id.in_(sessoes_ids))
        .group_by(ConvocacaoAssiduidade.sessao_id)
        .all()
    ) if sessoes_ids else {}
    sessoes_registo = []
    for sessao in sessoes:
        registados = contagens.get(sessao.id, 0)
        total_sessao = total_jogadores_ativos + convocacoes_por_sessao.get(sessao.id, 0)
        if total_sessao and registados >= total_sessao:
            estado_registo = "concluida"
        elif registados:
            estado_registo = "parcial"
        else:
            estado_registo = "por_registar"
        sessoes_registo.append({
            "sessao": enriquecer_sessao_para_ui(sessao),
            "registados": registados,
            "total": total_sessao,
            "estado": estado_registo,
        })
    relatorio["sessoes_registo"] = sessoes_registo
    return templates.TemplateResponse(
        request,
        "assiduidade/equipa.html",
        _contexto_relatorio_equipa(request, equipa, relatorio, utilizador),
    )


@router.get("/equipas/{equipa_id}/pdf")
def exportar_pdf_assiduidade_equipa(
    equipa_id: int,
    request: Request,
    inicio: str = "",
    fim: str = "",
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    verificar_ou_negar_equipa(utilizador, equipa_id, db)
    equipa = db.query(Equipa).filter(Equipa.id == equipa_id).first()
    if not equipa:
        return RedirectResponse(url="/equipas")

    relatorio = obter_relatorio_assiduidade_equipa(
        db,
        equipa_id,
        _data_query(inicio),
        _data_query(fim),
    )
    contexto = _contexto_relatorio_equipa(request, equipa, relatorio, utilizador)
    pdf_bytes = renderizar_pdf(request, "assiduidade/equipa_pdf.html", contexto)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=assiduidade_{equipa.id}.pdf"},
    )


@router.get("/sessoes/{sessao_id}", response_class=HTMLResponse)
def pagina_assiduidade(
    sessao_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    sessao = db.query(SessaoTreino).filter(SessaoTreino.id == sessao_id).first()
    if not sessao:
        return RedirectResponse(url="/equipas")
    sessao = enriquecer_sessao_para_ui(sessao)

    equipa = sessao.microciclo.mesociclo.macrociclo.equipa
    verificar_ou_negar_equipa(utilizador, equipa.id, db)

    sessoes_equipa = [
        enriquecer_sessao_para_ui(item)
        for item in _sessoes_assiduidade_equipa(db, equipa.id)
    ]

    jogadores, convocados = _jogadores_folha_assiduidade(db, equipa, sessao_id)
    jogadores_disponiveis_convocatoria = _jogadores_disponiveis_para_convocatoria(
        db,
        equipa,
        sessao_id,
    )

    registos = db.query(RegistoAssiduidade).filter(
        RegistoAssiduidade.sessao_id == sessao_id
    ).all()
    registos_dict = {r.jogador_id: r for r in registos}

    resumo = calcular_resumo_assiduidade(registos)
    resumo["registados"] = len(registos)
    resumo["por_registar"] = max(len(jogadores) - len(registos), 0)
    resumo["por_estado"]["por_registar"] = resumo["por_registar"]
    resumo["percentagem_esperada"] = round(
        (resumo["presentes"] / len(jogadores)) * 100,
        1,
    ) if jogadores else 0
    for registo in registos:
        registo.estado_visual = estado_assiduidade_visual(registo.estado, registo.presente)

    return templates.TemplateResponse(request, "assiduidade/sessao.html", {
        "utilizador": utilizador,
        "sessao": sessao,
        "equipa": equipa,
        "sessoes_equipa": sessoes_equipa,
        "jogadores": jogadores,
        "convocados": convocados,
        "jogadores_disponiveis_convocatoria": jogadores_disponiveis_convocatoria,
        "registos_dict": registos_dict,
        "total_presentes": resumo["presentes"],
        "total_jogadores": len(jogadores),
        "percentagem": resumo["percentagem"],
        "resumo_assiduidade": resumo,
        "estados_assiduidade": ESTADOS_ASSIDUIDADE,
        "estados_assiduidade_visual": ESTADOS_ASSIDUIDADE_VISUAL,
    })


@router.post("/sessoes/{sessao_id}/convocados")
async def adicionar_convocados_assiduidade(
    sessao_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    """Adiciona atletas de outras equipas somente à folha desta sessão."""
    sessao = db.query(SessaoTreino).filter(SessaoTreino.id == sessao_id).first()
    if not sessao:
        return RedirectResponse(url="/equipas", status_code=303)
    equipa = sessao.microciclo.mesociclo.macrociclo.equipa
    verificar_ou_negar_equipa(utilizador, equipa.id, db)

    dados = await request.form()
    ids = {
        int(valor)
        for valor in dados.getlist("jogador_id")
        if str(valor).strip().isdigit()
    }
    if not ids:
        set_flash(request, "Seleciona pelo menos um atleta para convocar.", "error")
        return RedirectResponse(url=f"/assiduidade/sessoes/{sessao_id}", status_code=303)

    existentes = {
        jogador_id
        for jogador_id, in db.query(ConvocacaoAssiduidade.jogador_id).filter(
            ConvocacaoAssiduidade.sessao_id == sessao_id,
            ConvocacaoAssiduidade.clube_id == equipa.clube_id,
        ).all()
    }
    jogadores = db.query(Jogador).filter(
        Jogador.id.in_(ids),
        Jogador.clube_id == equipa.clube_id,
        Jogador.ativo.is_(True),
    ).all()
    adicionados = 0
    for jogador in jogadores:
        if jogador.equipa_id == equipa.id or jogador.id in existentes:
            continue
        db.add(ConvocacaoAssiduidade(
            clube_id=equipa.clube_id,
            sessao_id=sessao_id,
            jogador_id=jogador.id,
        ))
        adicionados += 1
    db.commit()
    set_flash(
        request,
        f"{adicionados} atleta(s) adicionado(s) à folha deste treino." if adicionados else "Os atletas selecionados já estavam convocados.",
    )
    return RedirectResponse(url=f"/assiduidade/sessoes/{sessao_id}", status_code=303)


@router.post("/sessoes/{sessao_id}/convocados/{jogador_id}/eliminar")
def remover_convocado_assiduidade(
    sessao_id: int,
    jogador_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    """Retira a convocatória e qualquer registo desse atleta nesta sessão."""
    sessao = db.query(SessaoTreino).filter(SessaoTreino.id == sessao_id).first()
    if not sessao:
        return RedirectResponse(url="/equipas", status_code=303)
    equipa = sessao.microciclo.mesociclo.macrociclo.equipa
    verificar_ou_negar_equipa(utilizador, equipa.id, db)

    convocacao = db.query(ConvocacaoAssiduidade).filter(
        ConvocacaoAssiduidade.sessao_id == sessao_id,
        ConvocacaoAssiduidade.jogador_id == jogador_id,
        ConvocacaoAssiduidade.clube_id == equipa.clube_id,
    ).first()
    if convocacao:
        db.delete(convocacao)
        db.query(RegistoAssiduidade).filter(
            RegistoAssiduidade.sessao_id == sessao_id,
            RegistoAssiduidade.jogador_id == jogador_id,
        ).delete(synchronize_session=False)
        db.commit()
        set_flash(request, "Convocatória retirada deste treino.")
    return RedirectResponse(url=f"/assiduidade/sessoes/{sessao_id}", status_code=303)


@router.post("/sessoes/{sessao_id}")
async def guardar_assiduidade(
    sessao_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    sessao_check = db.query(SessaoTreino).filter(SessaoTreino.id == sessao_id).first()
    if not sessao_check:
        return RedirectResponse(url="/equipas", status_code=303)
    equipa_check = sessao_check.microciclo.mesociclo.macrociclo.equipa
    verificar_ou_negar_equipa(utilizador, equipa_check.id, db)

    dados = await request.form()

    registos = db.query(RegistoAssiduidade).filter(
        RegistoAssiduidade.sessao_id == sessao_id
    ).all()
    registos_por_jogador = {registo.jogador_id: registo for registo in registos}
    equipa = sessao_check.microciclo.mesociclo.macrociclo.equipa
    jogadores, _ = _jogadores_folha_assiduidade(db, equipa, sessao_id)

    dados_validados = []
    try:
        for jogador in jogadores:
            estado = normalizar_estado_assiduidade(
                dados.get(f"estado_{jogador.id}"),
                dados.get(f"presente_{jogador.id}") == "on",
            )
            rpe = _normalizar_rpe_individual(dados.get(f"rpe_{jogador.id}"))
            if not estado_para_presenca(estado):
                rpe = None
            dados_validados.append((jogador, estado, rpe))
    except ValueError as erro:
        set_flash(request, str(erro), "error")
        return RedirectResponse(url=f"/assiduidade/sessoes/{sessao_id}", status_code=303)

    for jogador, estado, rpe in dados_validados:
        registo = registos_por_jogador.get(jogador.id)
        if estado == "por_registar":
            if registo:
                db.delete(registo)
            continue
        if not registo:
            registo = RegistoAssiduidade(
                sessao_id=sessao_id,
                jogador_id=jogador.id,
                clube_id=equipa.clube_id,
            )
            db.add(registo)
        motivo = dados.get(f"motivo_{jogador.id}", "")
        registo.estado = estado
        registo.presente = estado_para_presenca(estado)
        registo.motivo_falta = motivo if not registo.presente and motivo else None
        registo.rpe_individual = rpe

    if sessao_check and normalizar_estado_sessao(sessao_check.estado) == "executada" and all(
        normalizar_estado_assiduidade(
            dados.get(f"estado_{jogador.id}"),
            dados.get(f"presente_{jogador.id}") == "on",
        ) != "por_registar"
        for jogador, _, _ in dados_validados
    ):
        sessao_check.estado = "registada"
    db.commit()
    set_flash(request, "Assiduidade guardada com sucesso.")
    return RedirectResponse(url=f"/assiduidade/sessoes/{sessao_id}", status_code=303)

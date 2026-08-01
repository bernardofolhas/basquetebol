from datetime import date, datetime, timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from auth import verificar_acesso_equipa, verificar_perfil
from auth_deps import AcessoNegado, exigir_autenticacao
from database import get_db
from flash import set_flash
from horarios import hora_eh_anterior, normalizar_hora
from models.equipa import Equipa
from models.espaco_treino import EspacoTreino
from models.planeamento import Macrociclo, Mesociclo, Microciclo, SessaoTreino
from models.planeamento_clube import (
    EventoPlaneamentoClube,
    OrigemEventoPlaneamentoClubeEnum,
    TipoEventoPlaneamentoClubeEnum,
)
from services.agenda_service import conflitos_do_evento, metadados_tipo_agenda


router = APIRouter(prefix="/agenda")


def _datas_recorrencia(inicio: date, fim: date | None, frequencia: str, intervalo: int) -> list[date]:
    if not fim or fim < inicio:
        return [inicio]
    if (fim - inicio).days > 730:
        raise ValueError("Uma programação não pode exceder dois anos.")
    frequencia = (frequencia or "unica").strip().lower()
    if frequencia == "unica":
        return [inicio]
    passos = {"diaria": 1, "semanal": 7, "quinzenal": 14}
    if frequencia not in passos:
        raise ValueError("Seleciona uma frequência de recorrência válida.")
    passo = timedelta(days=passos[frequencia] * max(1, min(intervalo, 12)))
    datas, cursor = [], inicio
    while cursor <= fim:
        datas.append(cursor)
        cursor += passo
    return datas


def _id(valor: str | int | None) -> int | None:
    if valor in (None, ""):
        return None
    try:
        return int(valor)
    except (TypeError, ValueError):
        raise ValueError("O identificador indicado não é válido.") from None


def _data(valor: str | None) -> date:
    try:
        return date.fromisoformat((valor or "").strip())
    except (TypeError, ValueError):
        raise ValueError("A data da atividade não é válida.") from None


def _horas(hora_inicio: str | None, hora_fim: str | None) -> tuple[str | None, str | None]:
    inicio = normalizar_hora(hora_inicio) if hora_inicio else None
    fim = normalizar_hora(hora_fim) if hora_fim else None
    if hora_inicio and not inicio or hora_fim and not fim:
        raise ValueError("As horas devem estar no formato HH:MM.")
    if inicio and fim and not hora_eh_anterior(inicio, fim):
        raise ValueError("A hora de início deve ser anterior à hora de término.")
    return inicio, fim


def _url_contexto(
    *,
    macrociclo_id: int | None = None,
    mesociclo_id: int | None = None,
    microciclo_id: int | None = None,
    retorno: str | None = None,
) -> str:
    if retorno and retorno.startswith("/") and not retorno.startswith("//"):
        return retorno
    if microciclo_id:
        return f"/planeamento/microciclos/{microciclo_id}"
    if mesociclo_id:
        return f"/planeamento/mesociclos/{mesociclo_id}"
    if macrociclo_id:
        return f"/planeamento/macrociclos/{macrociclo_id}"
    return "/calendario"


def _resolver_contexto(
    db: Session,
    equipa_id: int | None,
    macrociclo_id: int | None,
    mesociclo_id: int | None,
    microciclo_id: int | None,
):
    macrociclo = db.query(Macrociclo).filter(Macrociclo.id == macrociclo_id).first() if macrociclo_id else None
    mesociclo = db.query(Mesociclo).filter(Mesociclo.id == mesociclo_id).first() if mesociclo_id else None
    microciclo = db.query(Microciclo).filter(Microciclo.id == microciclo_id).first() if microciclo_id else None

    if macrociclo and equipa_id and macrociclo.equipa_id != equipa_id:
        raise ValueError("O macrociclo não pertence à equipa indicada.")
    if mesociclo and (macrociclo and mesociclo.macrociclo_id != macrociclo.id):
        raise ValueError("O mesociclo não pertence ao macrociclo indicado.")
    if microciclo and (mesociclo and microciclo.mesociclo_id != mesociclo.id):
        raise ValueError("O microciclo não pertence ao mesociclo indicado.")

    if microciclo:
        mesociclo = mesociclo or microciclo.mesociclo
        macrociclo = macrociclo or mesociclo.macrociclo
    if mesociclo:
        macrociclo = macrociclo or mesociclo.macrociclo
    if macrociclo:
        equipa_id = equipa_id or macrociclo.equipa_id
    return equipa_id, macrociclo, mesociclo, microciclo


def _verificar_acesso(utilizador, equipa_id: int | None, db: Session, aplica_a_todas: bool = False) -> None:
    if aplica_a_todas:
        if not verificar_perfil(utilizador, ["administrador", "coordenador"]):
            raise AcessoNegado("/dashboard")
        return
    if not equipa_id or not verificar_acesso_equipa(utilizador, equipa_id, db):
        raise AcessoNegado("/equipas")


def _obter_espaco_nome(db: Session, espaco_id: int | None) -> str | None:
    if not espaco_id:
        return None
    espaco = db.query(EspacoTreino).filter(EspacoTreino.id == espaco_id).first()
    return espaco.nome if espaco else None


def _criar_sessao_se_necessario(
    db: Session,
    evento: EventoPlaneamentoClube,
    microciclo: Microciclo | None,
    tipo: str,
    equipa_id: int | None,
) -> None:
    if not microciclo or tipo not in {
        TipoEventoPlaneamentoClubeEnum.treino_equipa.value,
        TipoEventoPlaneamentoClubeEnum.treino_individual.value,
        TipoEventoPlaneamentoClubeEnum.jogo.value,
    }:
        return
    e_jogo = tipo == TipoEventoPlaneamentoClubeEnum.jogo.value
    numero = None
    if not e_jogo:
        numero = db.query(SessaoTreino).filter(
            SessaoTreino.microciclo_id == microciclo.id,
            SessaoTreino.e_jogo.is_(False),
        ).count() + 1
    sessao = SessaoTreino(
        data=evento.data,
        local=_obter_espaco_nome(db, evento.espaco_id),
        hora_inicio=evento.hora_inicio,
        hora_fim=evento.hora_fim,
        numero_treino=numero,
        e_jogo=e_jogo,
        origem="manual",
        sincronizada=False,
        alterada_manual=True,
        ativa=True,
        estado="planeada",
        microciclo_id=microciclo.id,
        plano_semanal_clube_id=evento.plano_semanal_id,
        evento_planeamento_clube=evento,
    )
    db.add(sessao)


def _atualizar_sessao_ligada(db: Session, evento: EventoPlaneamentoClube, tipo: str) -> None:
    for sessao in evento.sessoes_geradas:
        sessao.data = evento.data
        sessao.hora_inicio = evento.hora_inicio
        sessao.hora_fim = evento.hora_fim
        sessao.local = _obter_espaco_nome(db, evento.espaco_id)
        sessao.e_jogo = tipo == TipoEventoPlaneamentoClubeEnum.jogo.value
        sessao.alterada_manual = True
        sessao.sincronizada = False


def _preparar_evento(
    db: Session,
    utilizador,
    *,
    tipo: str,
    titulo: str,
    data_evento: str,
    hora_inicio: str,
    hora_fim: str,
    descricao: str,
    espaco_id: str,
    equipa_id: str,
    macrociclo_id: str,
    mesociclo_id: str,
    microciclo_id: str,
    aplica_a_todas_equipas: str,
    retorno: str,
    db_commit: bool = False,
) -> tuple[EventoPlaneamentoClube, str]:
    valores = {item.value for item in TipoEventoPlaneamentoClubeEnum}
    if tipo not in valores:
        raise ValueError("O tipo de atividade não é válido.")
    if not titulo.strip():
        raise ValueError("Indica um título para a atividade.")

    data_convertida = _data(data_evento)
    inicio, fim = _horas(hora_inicio, hora_fim)
    equipa_convertida = _id(equipa_id)
    macro_convertido = _id(macrociclo_id)
    meso_convertido = _id(mesociclo_id)
    micro_convertido = _id(microciclo_id)
    espaco_convertido = _id(espaco_id)
    aplica = aplica_a_todas_equipas == "true"
    equipa_convertida, macrociclo, mesociclo, microciclo = _resolver_contexto(
        db,
        equipa_convertida,
        macro_convertido,
        meso_convertido,
        micro_convertido,
    )
    _verificar_acesso(utilizador, equipa_convertida, db, aplica)

    evento = EventoPlaneamentoClube(
        tipo=TipoEventoPlaneamentoClubeEnum(tipo),
        titulo=titulo.strip(),
        descricao=descricao.strip() or None,
        data=data_convertida,
        hora_inicio=inicio,
        hora_fim=fim,
        planeamento_anual_id=None,
        planeamento_mensal_id=None,
        plano_semanal_id=None,
        macrociclo_id=macrociclo.id if macrociclo else macro_convertido,
        mesociclo_id=mesociclo.id if mesociclo else meso_convertido,
        microciclo_id=microciclo.id if microciclo else micro_convertido,
        equipa_id=None if aplica else equipa_convertida,
        espaco_id=espaco_convertido,
        aplica_a_todas_equipas=aplica,
        origem=OrigemEventoPlaneamentoClubeEnum.manual,
    )
    db.add(evento)
    db.flush()
    _criar_sessao_se_necessario(db, evento, microciclo, tipo, equipa_convertida)
    return evento, _url_contexto(
        macrociclo_id=evento.macrociclo_id,
        mesociclo_id=evento.mesociclo_id,
        microciclo_id=evento.microciclo_id,
        retorno=retorno,
    )


@router.post("/atividades")
async def criar_atividade_agenda(
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
    tipo: str = Form(...),
    titulo: str = Form(...),
    data_evento: str = Form(...),
    data_fim: str = Form(""),
    recorrencia: str = Form("unica"),
    recorrencia_intervalo: int = Form(1),
    hora_inicio: str = Form(""),
    hora_fim: str = Form(""),
    descricao: str = Form(""),
    espaco_id: str = Form(""),
    equipa_id: str = Form(""),
    macrociclo_id: str = Form(""),
    mesociclo_id: str = Form(""),
    microciclo_id: str = Form(""),
    aplica_a_todas_equipas: str = Form("false"),
    retorno: str = Form(""),
):
    try:
        inicio = _data(data_evento)
        fim = _data(data_fim) if data_fim else None
        datas = _datas_recorrencia(inicio, fim, recorrencia, recorrencia_intervalo)
        serie_id = str(uuid4()) if len(datas) > 1 else None
        conflitos = []
        destino = retorno or "/calendario"
        for data_ocorrencia in datas:
            evento, destino = _preparar_evento(
                db, utilizador, tipo=tipo, titulo=titulo, data_evento=data_ocorrencia.isoformat(),
                hora_inicio=hora_inicio, hora_fim=hora_fim, descricao=descricao, espaco_id=espaco_id,
                equipa_id=equipa_id, macrociclo_id=macrociclo_id, mesociclo_id=mesociclo_id,
                microciclo_id=microciclo_id, aplica_a_todas_equipas=aplica_a_todas_equipas, retorno=retorno,
            )
            evento.data_fim = fim
            evento.serie_id = serie_id
            evento.recorrencia_frequencia = recorrencia if serie_id else None
            evento.recorrencia_intervalo = recorrencia_intervalo if serie_id else None
            evento.alterado_por = utilizador.username
            conflitos.extend(conflitos_do_evento(db, evento))
        db.commit()
    except ValueError as erro:
        db.rollback()
        set_flash(request, str(erro), "error")
        return RedirectResponse(url=retorno or "/calendario", status_code=303)

    if conflitos:
        set_flash(request, f"Atividade criada com {len(conflitos)} conflito(s) de agenda. Revê o detalhe.", "error")
    else:
        sufixo = f" ({len(datas)} ocorrências)" if len(datas) > 1 else ""
        set_flash(request, f"{metadados_tipo_agenda(evento.tipo)['label']} criado com sucesso{sufixo}.")
    return RedirectResponse(url=destino, status_code=303)


@router.post("/atividades/{evento_id}/editar")
async def editar_atividade_agenda(
    evento_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
    tipo: str = Form(...),
    titulo: str = Form(...),
    data_evento: str = Form(...),
    data_fim: str = Form(""),
    escopo_recorrencia: str = Form("ocorrencia"),
    hora_inicio: str = Form(""),
    hora_fim: str = Form(""),
    descricao: str = Form(""),
    espaco_id: str = Form(""),
    equipa_id: str = Form(""),
    macrociclo_id: str = Form(""),
    mesociclo_id: str = Form(""),
    microciclo_id: str = Form(""),
    aplica_a_todas_equipas: str = Form("false"),
    retorno: str = Form(""),
):
    evento = db.query(EventoPlaneamentoClube).filter(EventoPlaneamentoClube.id == evento_id).first()
    if not evento:
        return RedirectResponse(url=retorno or "/calendario", status_code=303)
    try:
        tipo_valido = TipoEventoPlaneamentoClubeEnum(tipo)
        data_convertida = _data(data_evento)
        inicio, fim = _horas(hora_inicio, hora_fim)
        equipa_convertida, macrociclo, mesociclo, microciclo = _resolver_contexto(
            db,
            _id(equipa_id),
            _id(macrociclo_id),
            _id(mesociclo_id),
            _id(microciclo_id),
        )
        aplica = aplica_a_todas_equipas == "true"
        _verificar_acesso(utilizador, equipa_convertida or evento.equipa_id, db, aplica)
        if not titulo.strip():
            raise ValueError("Indica um título para a atividade.")
        alvos = [evento]
        if evento.serie_id and escopo_recorrencia in {"futuro", "serie"}:
            query = db.query(EventoPlaneamentoClube).filter(EventoPlaneamentoClube.serie_id == evento.serie_id, EventoPlaneamentoClube.ativo.is_(True))
            if escopo_recorrencia == "futuro":
                query = query.filter(EventoPlaneamentoClube.data >= evento.data)
            alvos = query.all()
        deslocamento = data_convertida - evento.data
        conflitos = []
        for alvo in alvos:
            alvo.tipo = tipo_valido
            alvo.titulo = titulo.strip()
            alvo.data = alvo.data + deslocamento
            alvo.data_fim = _data(data_fim) if data_fim else alvo.data_fim
            alvo.hora_inicio = inicio
            alvo.hora_fim = fim
            alvo.descricao = descricao.strip() or None
            alvo.espaco_id = _id(espaco_id)
            alvo.equipa_id = None if aplica else equipa_convertida
            alvo.aplica_a_todas_equipas = aplica
            alvo.macrociclo_id = macrociclo.id if macrociclo else _id(macrociclo_id)
            alvo.mesociclo_id = mesociclo.id if mesociclo else _id(mesociclo_id)
            alvo.microciclo_id = microciclo.id if microciclo else _id(microciclo_id)
            alvo.alterado_por = utilizador.username
            _atualizar_sessao_ligada(db, alvo, tipo)
            conflitos.extend(conflitos_do_evento(db, alvo))
        db.commit()
    except ValueError as erro:
        db.rollback()
        set_flash(request, str(erro), "error")
        return RedirectResponse(url=retorno or f"/planeamento-clube/eventos/{evento_id}", status_code=303)

    if conflitos:
        set_flash(request, f"Atividade atualizada com {len(conflitos)} conflito(s) de agenda.", "error")
    else:
        set_flash(request, "Atividade atualizada.")
    return RedirectResponse(url=_url_contexto(
        macrociclo_id=evento.macrociclo_id,
        mesociclo_id=evento.mesociclo_id,
        microciclo_id=evento.microciclo_id,
        retorno=retorno,
    ), status_code=303)


@router.post("/atividades/{evento_id}/apagar")
async def apagar_atividade_agenda(
    evento_id: int, request: Request, db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao), escopo_recorrencia: str = Form("ocorrencia"),
    retorno: str = Form(""),
):
    evento = db.query(EventoPlaneamentoClube).filter(EventoPlaneamentoClube.id == evento_id).first()
    if not evento:
        return RedirectResponse(url=retorno or "/calendario", status_code=303)
    _verificar_acesso(utilizador, evento.equipa_id, db, evento.aplica_a_todas_equipas)
    alvos = [evento]
    if evento.serie_id and escopo_recorrencia in {"futuro", "serie"}:
        query = db.query(EventoPlaneamentoClube).filter(EventoPlaneamentoClube.serie_id == evento.serie_id, EventoPlaneamentoClube.ativo.is_(True))
        if escopo_recorrencia == "futuro":
            query = query.filter(EventoPlaneamentoClube.data >= evento.data)
        alvos = query.all()
    for alvo in alvos:
        tem_historico = bool(alvo.sessoes_geradas or alvo.jogo_id or alvo.atividade_id)
        if tem_historico:
            alvo.ativo = False
            alvo.desativado_em = datetime.now()
            alvo.alterado_por = utilizador.username
        else:
            db.delete(alvo)
    db.commit()
    set_flash(request, f"{len(alvos)} atividade(s) removida(s) do calendário.")
    return RedirectResponse(url=retorno or "/calendario", status_code=303)


@router.post("/atividades/{evento_id}/duplicar")
async def duplicar_atividade_agenda(
    evento_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
    data_evento: str = Form(""),
    retorno: str = Form(""),
):
    evento = db.query(EventoPlaneamentoClube).filter(EventoPlaneamentoClube.id == evento_id).first()
    if not evento:
        return RedirectResponse(url=retorno or "/calendario", status_code=303)
    _verificar_acesso(utilizador, evento.equipa_id, db, evento.aplica_a_todas_equipas)
    copia = EventoPlaneamentoClube(
        tipo=evento.tipo,
        titulo=f"{evento.titulo} (cópia)",
        descricao=evento.descricao,
        data=_data(data_evento) if data_evento else evento.data,
        hora_inicio=evento.hora_inicio,
        hora_fim=evento.hora_fim,
        planeamento_anual_id=evento.planeamento_anual_id,
        planeamento_mensal_id=evento.planeamento_mensal_id,
        plano_semanal_id=evento.plano_semanal_id,
        macrociclo_id=evento.macrociclo_id,
        mesociclo_id=evento.mesociclo_id,
        microciclo_id=evento.microciclo_id,
        equipa_id=evento.equipa_id,
        espaco_id=evento.espaco_id,
        treinador_id=evento.treinador_id,
        aplica_a_todas_equipas=evento.aplica_a_todas_equipas,
        origem=OrigemEventoPlaneamentoClubeEnum.manual,
        observacoes=evento.observacoes,
    )
    db.add(copia)
    db.flush()
    microciclo = db.query(Microciclo).filter(Microciclo.id == copia.microciclo_id).first() if copia.microciclo_id else None
    _criar_sessao_se_necessario(db, copia, microciclo, copia.tipo.value, copia.equipa_id)
    db.commit()
    set_flash(request, "Atividade duplicada.")
    return RedirectResponse(url=_url_contexto(
        macrociclo_id=copia.macrociclo_id,
        mesociclo_id=copia.mesociclo_id,
        microciclo_id=copia.microciclo_id,
        retorno=retorno,
    ), status_code=303)

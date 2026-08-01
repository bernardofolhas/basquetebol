import calendar
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy.orm import Session

from models.atribuicao_espaco_semanal import (
    AtribuicaoEspacoSemanal,
    EstadoAtribuicaoEspacoEnum,
)
from models.equipa import Equipa
from models.espaco_treino import EspacoTreino
from models.jogador import Jogador
from models.jogo import Jogo
from models.planeamento import SessaoTreino
from models.planeamento_clube import (
    EventoPlaneamentoClube,
    PlaneamentoClubeMensal,
    PlanoSemanalClube,
    TipoEventoPlaneamentoClubeEnum,
)


def obter_nome_mes_portugues(mes: int) -> str:
    """Converte o número do mês para um nome legível em português."""
    meses = {
        1: "Janeiro",
        2: "Fevereiro",
        3: "Março",
        4: "Abril",
        5: "Maio",
        6: "Junho",
        7: "Julho",
        8: "Agosto",
        9: "Setembro",
        10: "Outubro",
        11: "Novembro",
        12: "Dezembro",
    }
    return meses.get(mes, str(mes))


def obter_intervalo_mes(ano: int, mes: int) -> tuple[date, date]:
    """Calcula o primeiro e o último dia de um mês."""
    ultimo_dia = calendar.monthrange(ano, mes)[1]
    return date(ano, mes, 1), date(ano, mes, ultimo_dia)


def obter_intervalo_semana_referencia(referencia: date | None = None) -> tuple[date, date]:
    """Calcula o intervalo semanal operativo com base numa data de referência."""
    referencia = referencia or date.today()
    data_inicio = referencia - timedelta(days=referencia.weekday())
    data_fim = data_inicio + timedelta(days=6)
    return data_inicio, data_fim


def obter_plano_semanal_operacional(db: Session, referencia: date | None = None) -> PlanoSemanalClube | None:
    """Obtém o plano semanal mais relevante para a operação atual."""
    referencia = referencia or date.today()

    semanal_atual = db.query(PlanoSemanalClube).filter(
        PlanoSemanalClube.data_inicio <= referencia,
        PlanoSemanalClube.data_fim >= referencia,
    ).order_by(
        PlanoSemanalClube.data_inicio.desc(),
        PlanoSemanalClube.id.desc(),
    ).first()
    if semanal_atual:
        return semanal_atual

    semanal_futuro = db.query(PlanoSemanalClube).filter(
        PlanoSemanalClube.data_inicio >= referencia,
    ).order_by(
        PlanoSemanalClube.data_inicio.asc(),
        PlanoSemanalClube.id.asc(),
    ).first()
    if semanal_futuro:
        return semanal_futuro

    return db.query(PlanoSemanalClube).order_by(
        PlanoSemanalClube.data_fim.desc(),
        PlanoSemanalClube.id.desc(),
    ).first()


def obter_intervalo_operacional_semana(
    db: Session,
    referencia: date | None = None,
) -> tuple[PlanoSemanalClube | None, date, date]:
    """Resolve o intervalo semanal operativo com plano associado quando existir."""
    referencia = referencia or date.today()
    plano = obter_plano_semanal_operacional(db, referencia)
    if plano:
        return plano, plano.data_inicio, plano.data_fim

    data_inicio, data_fim = obter_intervalo_semana_referencia(referencia)
    return None, data_inicio, data_fim


def _obter_hora_ordenacao(hora: str | None) -> str:
    """Normaliza a hora para ordenação textual simples."""
    return hora or "99:99"


def _formar_intervalo_hora(hora_inicio: str | None, hora_fim: str | None) -> str:
    """Monta uma representação textual simples para um intervalo horário."""
    if hora_inicio and hora_fim:
        return f"{hora_inicio}-{hora_fim}"
    if hora_inicio:
        return hora_inicio
    if hora_fim:
        return hora_fim
    return "Hora por definir"


def _converter_hora_para_minutos(hora: str | None) -> int:
    """Converte um HH:MM simples em minutos totais."""
    if not hora or ":" not in hora:
        return 0
    horas, minutos = hora.split(":", 1)
    if not horas.isdigit() or not minutos.isdigit():
        return 0
    return int(horas) * 60 + int(minutos)


def _calcular_duracao_atribuicao_minutos(atribuicao: AtribuicaoEspacoSemanal) -> int:
    """Calcula a duração em minutos de uma atribuição simples."""
    return max(0, _converter_hora_para_minutos(atribuicao.hora_fim) - _converter_hora_para_minutos(atribuicao.hora_inicio))


def _obter_ids_equipas_evento(evento: EventoPlaneamentoClube, equipas_ids_todas: list[int]) -> list[int]:
    """Resolve as equipas alvo de um evento global."""
    if evento.aplica_a_todas_equipas:
        return equipas_ids_todas

    ids = []
    if evento.equipa_id:
        ids.append(evento.equipa_id)
    ids.extend(equipa.id for equipa in evento.equipas)
    return list(dict.fromkeys(ids))


def _obter_ids_equipas_atribuicao(
    atribuicao: AtribuicaoEspacoSemanal,
    equipas_ids_todas: list[int],
) -> list[int]:
    """Resolve as equipas alvo de uma atribuição semanal."""
    if atribuicao.equipa_id:
        return [atribuicao.equipa_id]
    if atribuicao.evento:
        return _obter_ids_equipas_evento(atribuicao.evento, equipas_ids_todas)
    return []


def _obter_tipo_treino_evento_ou_atribuicao(
    evento: EventoPlaneamentoClube | None,
    atribuicao: AtribuicaoEspacoSemanal | None = None,
) -> str:
    """Traduz o tipo técnico para uma label operacional legível."""
    if evento and evento.tipo == TipoEventoPlaneamentoClubeEnum.treino_individual:
        return "Treino individual"
    if evento and evento.tipo == TipoEventoPlaneamentoClubeEnum.treino_equipa:
        return "Treino equipa"
    if atribuicao and getattr(atribuicao.tipo_ocupacao, "value", None):
        return atribuicao.tipo_ocupacao.value.replace("_", " ").capitalize()
    return "Treino"


def _listar_eventos_operacionais_mensal(
    db: Session,
    mensal: PlaneamentoClubeMensal,
) -> tuple[list[PlanoSemanalClube], list[EventoPlaneamentoClube], list[AtribuicaoEspacoSemanal]]:
    """Obtém semanais, eventos e atribuições relevantes para um mensal."""
    semanais = db.query(PlanoSemanalClube).filter(
        PlanoSemanalClube.planeamento_mensal_id == mensal.id
    ).order_by(PlanoSemanalClube.data_inicio.asc(), PlanoSemanalClube.id.asc()).all()

    semanais_ids = [semanal.id for semanal in semanais]

    eventos_mensais = db.query(EventoPlaneamentoClube).filter(
        EventoPlaneamentoClube.planeamento_mensal_id == mensal.id
    ).all()
    eventos_semanais = []
    atribuicoes = []

    if semanais_ids:
        eventos_semanais = db.query(EventoPlaneamentoClube).filter(
            EventoPlaneamentoClube.plano_semanal_id.in_(semanais_ids)
        ).all()
        atribuicoes = db.query(AtribuicaoEspacoSemanal).filter(
            AtribuicaoEspacoSemanal.plano_semanal_id.in_(semanais_ids),
            AtribuicaoEspacoSemanal.estado != EstadoAtribuicaoEspacoEnum.cancelado,
        ).all()

    eventos = [*eventos_mensais, *eventos_semanais]
    eventos.sort(key=lambda evento: (evento.data, _obter_hora_ordenacao(evento.hora_inicio), evento.id))
    atribuicoes.sort(key=lambda atribuicao: (atribuicao.data, _obter_hora_ordenacao(atribuicao.hora_inicio), atribuicao.id))
    return semanais, eventos, atribuicoes


def obter_resumo_operacional_mensal(
    db: Session,
    mensal: PlaneamentoClubeMensal,
    data_minima: date | None = None,
) -> dict:
    """Constrói um resumo operacional do mensal legível para coordenador."""
    data_inicio, data_fim = obter_intervalo_mes(mensal.ano, mensal.mes)
    semanais, eventos, atribuicoes = _listar_eventos_operacionais_mensal(db, mensal)
    jogos_mes = db.query(Jogo).filter(
        Jogo.data >= data_inicio,
        Jogo.data <= data_fim,
    ).order_by(Jogo.data.asc(), Jogo.hora.asc(), Jogo.id.asc()).all()

    equipas = db.query(Equipa).order_by(Equipa.nome.asc()).all()
    equipas_ids_todas = [equipa.id for equipa in equipas]
    resumo_equipas = []
    jogos_por_equipa = defaultdict(list)
    treinos_por_equipa = defaultdict(list)
    chaves_treinos_por_equipa = defaultdict(set)

    for jogo in jogos_mes:
        if data_minima and jogo.data < data_minima:
            continue
        jogos_por_equipa[jogo.equipa_id].append(jogo)

    eventos_por_id = {evento.id: evento for evento in eventos}

    for atribuicao in atribuicoes:
        if atribuicao.data < data_inicio or atribuicao.data > data_fim:
            continue
        if data_minima and atribuicao.data < data_minima:
            continue

        evento = eventos_por_id.get(atribuicao.evento_id) if atribuicao.evento_id else None
        equipa_ids = _obter_ids_equipas_atribuicao(atribuicao, equipas_ids_todas)
        if not equipa_ids:
            continue

        treino = {
            "data": atribuicao.data,
            "hora": _formar_intervalo_hora(atribuicao.hora_inicio, atribuicao.hora_fim),
            "espaco": atribuicao.espaco.nome if atribuicao.espaco else "Espaço por definir",
            "tipo": _obter_tipo_treino_evento_ou_atribuicao(evento, atribuicao),
            "origem": "atribuicao",
        }
        chave_treino = (treino["data"], treino["hora"], treino["espaco"], treino["tipo"])

        for equipa_id in equipa_ids:
            if chave_treino in chaves_treinos_por_equipa[equipa_id]:
                continue
            chaves_treinos_por_equipa[equipa_id].add(chave_treino)
            treinos_por_equipa[equipa_id].append(treino)

    for evento in eventos:
        if evento.data < data_inicio or evento.data > data_fim:
            continue
        if data_minima and evento.data < data_minima:
            continue
        if evento.tipo not in {
            TipoEventoPlaneamentoClubeEnum.treino_equipa,
            TipoEventoPlaneamentoClubeEnum.treino_individual,
        }:
            continue

        equipa_ids = _obter_ids_equipas_evento(evento, equipas_ids_todas)
        treino = {
            "data": evento.data,
            "hora": _formar_intervalo_hora(evento.hora_inicio, evento.hora_fim),
            "espaco": evento.espaco.nome if evento.espaco else "Espaço por definir",
            "tipo": _obter_tipo_treino_evento_ou_atribuicao(evento),
            "origem": "evento",
        }
        chave_treino = (treino["data"], treino["hora"], treino["espaco"], treino["tipo"])

        for equipa_id in equipa_ids:
            if chave_treino in chaves_treinos_por_equipa[equipa_id]:
                continue
            chaves_treinos_por_equipa[equipa_id].add(chave_treino)
            treinos_por_equipa[equipa_id].append(treino)

    for equipa_id in treinos_por_equipa:
        treinos_por_equipa[equipa_id].sort(key=lambda treino: (treino["data"], treino["hora"], treino["espaco"]))

    for equipa in equipas:
        treinador_principal = None
        if equipa.treinadores:
            treinador_principal = sorted(equipa.treinadores, key=lambda treinador: treinador.nome.lower())[0]

        treinos_equipa = treinos_por_equipa.get(equipa.id, [])
        jogos_equipa = jogos_por_equipa.get(equipa.id, [])
        resumo_equipas.append({
            "equipa": equipa,
            "treinador_principal": treinador_principal,
            "treinos": treinos_equipa,
            "jogos": jogos_equipa,
            "total_treinos": len(treinos_equipa),
            "total_jogos": len(jogos_equipa),
        })

    total_treinos = sum(item["total_treinos"] for item in resumo_equipas)
    total_jogos = sum(item["total_jogos"] for item in resumo_equipas)

    return {
        "mensal": mensal,
        "periodo": {
            "inicio": data_inicio,
            "fim": data_fim,
            "nome_mes": obter_nome_mes_portugues(mensal.mes),
            "label": f"{obter_nome_mes_portugues(mensal.mes)} {mensal.ano}",
        },
        "semanais": semanais,
        "eventos": eventos,
        "atribuicoes": atribuicoes,
        "jogos_mes": jogos_mes,
        "resumo_equipas": resumo_equipas,
        "estatisticas": {
            "total_equipas": len(resumo_equipas),
            "total_treinos": total_treinos,
            "total_jogos": total_jogos,
            "total_semanais": len(semanais),
        },
    }


def construir_mapa_espacos_semanal(atribuicoes: list[AtribuicaoEspacoSemanal]) -> dict:
    """Traduz atribuições da semana para um mapa operacional e detecta conflitos."""
    mapa = []
    conflitos = []
    atribuicoes_ordenadas = sorted(
        atribuicoes,
        key=lambda atribuicao: (
            atribuicao.data,
            atribuicao.espaco.nome if atribuicao.espaco else "",
            _obter_hora_ordenacao(atribuicao.hora_inicio),
            atribuicao.id,
        ),
    )

    agrupadas = defaultdict(list)
    for atribuicao in atribuicoes_ordenadas:
        mapa.append({
            "dia": atribuicao.data,
            "hora": _formar_intervalo_hora(atribuicao.hora_inicio, atribuicao.hora_fim),
            "espaco": atribuicao.espaco.nome if atribuicao.espaco else "Espaço por definir",
            "equipa": atribuicao.equipa.nome if atribuicao.equipa else "Sem equipa definida",
            "tipo": atribuicao.tipo_ocupacao.value.replace("_", " ").capitalize() if getattr(atribuicao.tipo_ocupacao, "value", None) else "Ocupação",
            "evento": atribuicao.evento.titulo if atribuicao.evento else None,
            "estado": atribuicao.estado.value if getattr(atribuicao.estado, "value", None) else str(atribuicao.estado),
            "atribuicao": atribuicao,
        })
        agrupadas[(atribuicao.data, atribuicao.espaco_id)].append(atribuicao)

    for (_, _), itens in agrupadas.items():
        itens_ordenados = sorted(itens, key=lambda item: (_obter_hora_ordenacao(item.hora_inicio), item.id))
        for indice, atual in enumerate(itens_ordenados):
            for seguinte in itens_ordenados[indice + 1:]:
                if atual.hora_fim <= seguinte.hora_inicio:
                    break
                conflitos.append({
                    "data": atual.data,
                    "espaco": atual.espaco.nome if atual.espaco else "Espaço por definir",
                    "atribuicao_a": atual,
                    "atribuicao_b": seguinte,
                    "mensagem": (
                        f"{atual.espaco.nome if atual.espaco else 'Espaço'} "
                        f"tem sobreposição em {atual.data}: "
                        f"{atual.hora_inicio}-{atual.hora_fim} e "
                        f"{seguinte.hora_inicio}-{seguinte.hora_fim}."
                    ),
                })

    conflitos.sort(key=lambda conflito: (conflito["data"], conflito["espaco"]))
    return {
        "mapa": mapa,
        "conflitos": conflitos,
    }


def obter_dashboard_ocupacao_espacos(db: Session, referencia: date | None = None) -> dict:
    """Constrói o dashboard operacional de ocupação de espaços."""
    plano_semanal, data_inicio, data_fim = obter_intervalo_operacional_semana(db, referencia)

    if plano_semanal:
        atribuicoes = db.query(AtribuicaoEspacoSemanal).filter(
            AtribuicaoEspacoSemanal.plano_semanal_id == plano_semanal.id,
            AtribuicaoEspacoSemanal.estado != EstadoAtribuicaoEspacoEnum.cancelado,
        ).order_by(
            AtribuicaoEspacoSemanal.data.asc(),
            AtribuicaoEspacoSemanal.hora_inicio.asc(),
        ).all()
    else:
        atribuicoes = db.query(AtribuicaoEspacoSemanal).filter(
            AtribuicaoEspacoSemanal.data >= data_inicio,
            AtribuicaoEspacoSemanal.data <= data_fim,
            AtribuicaoEspacoSemanal.estado != EstadoAtribuicaoEspacoEnum.cancelado,
        ).order_by(
            AtribuicaoEspacoSemanal.data.asc(),
            AtribuicaoEspacoSemanal.hora_inicio.asc(),
        ).all()

    mapa = construir_mapa_espacos_semanal(atribuicoes)
    espacos = db.query(EspacoTreino).order_by(EspacoTreino.nome.asc()).all()

    atribuicoes_por_espaco = defaultdict(list)
    for atribuicao in atribuicoes:
        atribuicoes_por_espaco[atribuicao.espaco_id].append(atribuicao)

    espacos_resumo = []
    for espaco in espacos:
        ocupacoes = atribuicoes_por_espaco.get(espaco.id, [])
        minutos_total = sum(_calcular_duracao_atribuicao_minutos(atribuicao) for atribuicao in ocupacoes)
        espacos_resumo.append({
            "espaco": espaco,
            "total_atribuicoes": len(ocupacoes),
            "total_horas": round(minutos_total / 60, 1),
            "ocupacoes": ocupacoes,
        })

    return {
        "plano_semanal": plano_semanal,
        "periodo": {
            "inicio": data_inicio,
            "fim": data_fim,
            "label": f"{data_inicio} → {data_fim}",
        },
        "espacos_resumo": espacos_resumo,
        "mapa_espacos": mapa["mapa"],
        "conflitos": mapa["conflitos"],
        "estatisticas": {
            "total_espacos": len(espacos),
            "total_atribuicoes": len(atribuicoes),
            "total_conflitos": len(mapa["conflitos"]),
            "horas_planeadas": round(sum(item["total_horas"] for item in espacos_resumo), 1),
        },
    }


def _obter_equipa_por_sessao(sessao: SessaoTreino):
    """Resolve a equipa de uma sessão mantendo tolerância a dados incompletos."""
    try:
        return sessao.microciclo.mesociclo.macrociclo.equipa
    except Exception:
        return None


def _listar_sessoes_periodo(
    db: Session,
    data_inicio: date,
    data_fim: date,
) -> list[SessaoTreino]:
    """Obtém sessões do período com ordenação simples."""
    return db.query(SessaoTreino).filter(
        SessaoTreino.data >= data_inicio,
        SessaoTreino.data <= data_fim,
    ).order_by(
        SessaoTreino.data.asc(),
        SessaoTreino.id.asc(),
    ).all()


def obter_dashboard_carga_treino(db: Session, referencia: date | None = None) -> dict:
    """Constrói o dashboard de carga de treino por equipa para a semana operacional."""
    plano_semanal, data_inicio, data_fim = obter_intervalo_operacional_semana(db, referencia)
    sessoes = [
        sessao for sessao in _listar_sessoes_periodo(db, data_inicio, data_fim)
        if not sessao.e_jogo and sessao.ativa
    ]

    distribuicao_base = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
    resumo_por_equipa = {}

    for sessao in sessoes:
        equipa = _obter_equipa_por_sessao(sessao)
        if not equipa:
            continue

        item = resumo_por_equipa.setdefault(equipa.id, {
            "equipa": equipa,
            "total_sessoes": 0,
            "volume_total": 0,
            "rpes": [],
            "distribuicao": {dia: 0 for dia in distribuicao_base},
            "sessoes": [],
        })
        item["total_sessoes"] += 1
        item["volume_total"] += sessao.volume_minutos or 0
        if sessao.intensidade_rpe is not None:
            item["rpes"].append(sessao.intensidade_rpe)
        item["distribuicao"][distribuicao_base[sessao.data.weekday()]] += 1
        item["sessoes"].append(sessao)

    resumo = list(resumo_por_equipa.values())
    for item in resumo:
        item["media_rpe"] = round(sum(item["rpes"]) / len(item["rpes"]), 1) if item["rpes"] else 0
    resumo.sort(key=lambda item: item["equipa"].nome)

    return {
        "plano_semanal": plano_semanal,
        "periodo": {
            "inicio": data_inicio,
            "fim": data_fim,
            "label": f"{data_inicio} → {data_fim}",
        },
        "resumo_equipas": resumo,
        "estatisticas": {
            "total_sessoes": len(sessoes),
            "total_equipas": len(resumo),
            "volume_total": sum(item["volume_total"] for item in resumo),
        },
        "distribuicao_base": distribuicao_base,
    }


def obter_dashboard_planeado_executado(db: Session, referencia: date | None = None) -> dict:
    """Constrói o dashboard simples de sessões planeadas, ativas e desativadas."""
    plano_semanal, data_inicio, data_fim = obter_intervalo_operacional_semana(db, referencia)
    sessoes = _listar_sessoes_periodo(db, data_inicio, data_fim)
    resumo_por_equipa = {}

    for sessao in sessoes:
        equipa = _obter_equipa_por_sessao(sessao)
        if not equipa:
            continue

        item = resumo_por_equipa.setdefault(equipa.id, {
            "equipa": equipa,
            "planeadas": 0,
            "ativas": 0,
            "desativadas": 0,
            "jogos": 0,
        })
        item["planeadas"] += 1
        if sessao.ativa:
            item["ativas"] += 1
        else:
            item["desativadas"] += 1
        if sessao.e_jogo:
            item["jogos"] += 1

    resumo = sorted(resumo_por_equipa.values(), key=lambda item: item["equipa"].nome)

    return {
        "plano_semanal": plano_semanal,
        "periodo": {
            "inicio": data_inicio,
            "fim": data_fim,
            "label": f"{data_inicio} → {data_fim}",
        },
        "resumo_equipas": resumo,
        "estatisticas": {
            "planeadas": len(sessoes),
            "ativas": len([sessao for sessao in sessoes if sessao.ativa]),
            "desativadas": len([sessao for sessao in sessoes if not sessao.ativa]),
            "jogos": len([sessao for sessao in sessoes if sessao.e_jogo]),
        },
    }


def obter_dashboard_sincronizacao(db: Session, referencia: date | None = None) -> dict:
    """Constrói o dashboard do estado de sincronização das sessões globais."""
    plano_semanal, data_inicio, data_fim = obter_intervalo_operacional_semana(db, referencia)

    if plano_semanal:
        sessoes = db.query(SessaoTreino).filter(
            SessaoTreino.plano_semanal_clube_id == plano_semanal.id,
            SessaoTreino.origem == "planeamento_global",
        ).order_by(SessaoTreino.data.asc(), SessaoTreino.id.asc()).all()
    else:
        sessoes = db.query(SessaoTreino).filter(
            SessaoTreino.origem == "planeamento_global",
            SessaoTreino.data >= data_inicio,
            SessaoTreino.data <= data_fim,
        ).order_by(SessaoTreino.data.asc(), SessaoTreino.id.asc()).all()

    resumo_por_equipa = {}
    for sessao in sessoes:
        equipa = _obter_equipa_por_sessao(sessao)
        if not equipa:
            continue

        item = resumo_por_equipa.setdefault(equipa.id, {
            "equipa": equipa,
            "sincronizadas": 0,
            "alteradas_manual": 0,
            "desatualizadas": 0,
            "desativadas": 0,
        })
        if not sessao.ativa:
            item["desativadas"] += 1
        elif sessao.alterada_manual:
            item["alteradas_manual"] += 1
        elif sessao.sincronizada:
            item["sincronizadas"] += 1
        else:
            item["desatualizadas"] += 1

    resumo = sorted(resumo_por_equipa.values(), key=lambda item: item["equipa"].nome)

    return {
        "plano_semanal": plano_semanal,
        "periodo": {
            "inicio": data_inicio,
            "fim": data_fim,
            "label": f"{data_inicio} → {data_fim}",
        },
        "resumo_equipas": resumo,
        "estatisticas": {
            "sincronizadas": len([sessao for sessao in sessoes if sessao.sincronizada and sessao.ativa and not sessao.alterada_manual]),
            "alteradas_manual": len([sessao for sessao in sessoes if sessao.alterada_manual and sessao.ativa]),
            "desatualizadas": len([sessao for sessao in sessoes if not sessao.sincronizada and not sessao.alterada_manual and sessao.ativa]),
            "desativadas": len([sessao for sessao in sessoes if not sessao.ativa]),
        },
        "ultima_sincronizacao": {
            "em": plano_semanal.ultima_sincronizacao_em if plano_semanal else None,
            "por": plano_semanal.ultima_sincronizacao_por if plano_semanal else None,
            "resumo": plano_semanal.ultima_sincronizacao_resumo if plano_semanal else None,
        },
    }


def obter_dashboard_clube_operacional(db: Session, referencia: date | None = None) -> dict:
    """Constrói o dashboard geral do clube com foco operacional."""
    referencia = referencia or date.today()
    plano_semanal, data_inicio, data_fim = obter_intervalo_operacional_semana(db, referencia)

    total_equipas = db.query(Equipa).count()
    total_jogadores = db.query(Jogador).count()
    total_sessoes_semana = db.query(SessaoTreino).filter(
        SessaoTreino.data >= data_inicio,
        SessaoTreino.data <= data_fim,
        SessaoTreino.ativa == True,
    ).count()
    total_jogos_semana = db.query(Jogo).filter(
        Jogo.data >= data_inicio,
        Jogo.data <= data_fim,
    ).count()

    dashboard_espacos = obter_dashboard_ocupacao_espacos(db, referencia)
    dashboard_carga = obter_dashboard_carga_treino(db, referencia)
    dashboard_execucao = obter_dashboard_planeado_executado(db, referencia)
    dashboard_sincronizacao = obter_dashboard_sincronizacao(db, referencia)

    alertas = []
    if dashboard_sincronizacao["estatisticas"]["desatualizadas"] > 0:
        alertas.append({
            "tipo": "sincronizacao",
            "urgente": True,
            "mensagem": (
                f"Existem {dashboard_sincronizacao['estatisticas']['desatualizadas']} "
                "sessões desatualizadas no plano semanal operacional."
            ),
        })
    if dashboard_espacos["estatisticas"]["total_conflitos"] > 0:
        alertas.append({
            "tipo": "espacos",
            "urgente": True,
            "mensagem": (
                f"Foram detetados {dashboard_espacos['estatisticas']['total_conflitos']} "
                "conflitos de ocupação de espaço."
            ),
        })
    if not alertas:
        alertas.append({
            "tipo": "operacao",
            "urgente": False,
            "mensagem": "Sem alertas operacionais críticos nesta semana.",
        })

    return {
        "plano_semanal": plano_semanal,
        "periodo": {
            "inicio": data_inicio,
            "fim": data_fim,
            "label": f"{data_inicio} → {data_fim}",
        },
        "kpis": {
            "total_equipas": total_equipas,
            "total_jogadores": total_jogadores,
            "total_sessoes_semana": total_sessoes_semana,
            "total_jogos_semana": total_jogos_semana,
        },
        "estado_plano": {
            "label": plano_semanal.estado.capitalize() if plano_semanal else "Sem plano semanal",
            "plano": plano_semanal,
        },
        "alertas_operacionais": alertas,
        "resumo_espacos": dashboard_espacos["estatisticas"],
        "resumo_carga": dashboard_carga["estatisticas"],
        "resumo_execucao": dashboard_execucao["estatisticas"],
        "resumo_sincronizacao": dashboard_sincronizacao["estatisticas"],
        "ultima_sincronizacao": dashboard_sincronizacao["ultima_sincronizacao"],
    }

import calendar
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy.orm import Session

from models.atividade import Atividade
from models.equipa import Equipa
from models.jogo import Jogo
from models.planeamento import Macrociclo, Mesociclo, Microciclo, SessaoTreino
from models.planeamento_clube import EventoPlaneamentoClube, TipoEventoPlaneamentoClubeEnum
from services.agenda_service import metadados_tipo_agenda
from services.sessao_workflow import estado_sessao_visual, proxima_acao_sessao, normalizar_estado_sessao

NOMES_DIAS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sab", "Dom"]
NOMES_MESES = [
    "",
    "Janeiro",
    "Fevereiro",
    "Marco",
    "Abril",
    "Maio",
    "Junho",
    "Julho",
    "Agosto",
    "Setembro",
    "Outubro",
    "Novembro",
    "Dezembro",
]

TIPOS_EVENTO_TREINO = {
    TipoEventoPlaneamentoClubeEnum.treino_equipa,
    TipoEventoPlaneamentoClubeEnum.treino_fisico,
    TipoEventoPlaneamentoClubeEnum.treino_individual,
}
TIPOS_EVENTO_SESSAO = TIPOS_EVENTO_TREINO | {TipoEventoPlaneamentoClubeEnum.jogo}
TIPOS_EVENTO_ATIVIDADE = {
    TipoEventoPlaneamentoClubeEnum.atividade_extra,
    TipoEventoPlaneamentoClubeEnum.evento_clube,
}


def _label_periodo(data_inicio: date, data_fim: date) -> str:
    if data_inicio == data_fim:
        return data_inicio.strftime("%d/%m/%Y")
    return f"{data_inicio.strftime('%d/%m/%Y')} -> {data_fim.strftime('%d/%m/%Y')}"


def _hora_para_ordenacao(hora: str | None) -> str:
    return hora or "99:99"


def _formatar_horario(hora_inicio: str | None, hora_fim: str | None) -> str:
    if hora_inicio and hora_fim:
        return f"{hora_inicio}-{hora_fim}"
    if hora_inicio:
        return hora_inicio
    if hora_fim:
        return f"ate {hora_fim}"
    return "Hora por definir"


def _obter_equipa_sessao(sessao: SessaoTreino):
    try:
        return sessao.microciclo.mesociclo.macrociclo.equipa
    except Exception:
        return None


def _evento_visivel_para_equipa(evento: EventoPlaneamentoClube, equipa_id: int) -> bool:
    if evento.aplica_a_todas_equipas:
        return True
    if evento.equipa_id == equipa_id:
        return True
    return any(equipa.id == equipa_id for equipa in evento.equipas)


def _estilo_item(categoria: str, origem: str | None = None) -> dict[str, str]:
    if categoria == "treino":
        return {
            "badge": "Treino",
            "pill_classes": "bg-emerald-100 text-emerald-800",
            "dot_classes": "bg-emerald-500",
            "card_classes": "border-emerald-100 bg-emerald-50",
        }
    if categoria == "jogo":
        return {
            "badge": "Jogo",
            "pill_classes": "bg-rose-100 text-rose-800",
            "dot_classes": "bg-rose-500",
            "card_classes": "border-rose-100 bg-rose-50",
        }
    if categoria == "atividade":
        return {
            "badge": "Atividade",
            "pill_classes": "bg-amber-100 text-amber-800",
            "dot_classes": "bg-amber-500",
            "card_classes": "border-amber-100 bg-amber-50",
        }
    if categoria == "recuperacao":
        return {
            "badge": "Folga",
            "pill_classes": "bg-sky-100 text-sky-800",
            "dot_classes": "bg-sky-500",
            "card_classes": "border-sky-100 bg-sky-50",
        }
    if categoria == "fisico":
        return {
            "badge": "Teste físico",
            "pill_classes": "bg-indigo-100 text-indigo-800",
            "dot_classes": "bg-indigo-500",
            "card_classes": "border-indigo-100 bg-indigo-50",
        }
    if categoria == "operacao":
        return {
            "badge": "Operação",
            "pill_classes": "bg-violet-100 text-violet-800",
            "dot_classes": "bg-violet-500",
            "card_classes": "border-violet-100 bg-violet-50",
        }
    return {
        "badge": origem or "Evento",
        "pill_classes": "bg-slate-100 text-slate-700",
        "dot_classes": "bg-slate-500",
        "card_classes": "border-slate-100 bg-slate-50",
    }


def _criar_item_base(
    *,
    item_id: str,
    categoria: str,
    subtipo: str,
    titulo: str,
    data_item: date,
    hora_inicio: str | None,
    hora_fim: str | None,
    local: str | None,
    equipa_nome: str | None,
    equipa_escalao: str | None,
    origem_label: str,
    detalhe: str | None,
    link: str | None = None,
) -> dict:
    estilo = _estilo_item(categoria, origem_label)
    return {
        "id": item_id,
        "categoria": categoria,
        "subtipo": subtipo,
        "titulo": titulo,
        "data": data_item,
        "hora_inicio": hora_inicio,
        "hora_fim": hora_fim,
        "horario": _formatar_horario(hora_inicio, hora_fim),
        "local": local or "Local por definir",
        "equipa_nome": equipa_nome,
        "equipa_escalao": equipa_escalao,
        "origem_label": origem_label,
        "detalhe": detalhe,
        "link": link,
        "dia_semana": NOMES_DIAS[data_item.weekday()],
        "mes_label": f"{NOMES_MESES[data_item.month]} {data_item.year}",
        "badge": estilo["badge"],
        "pill_classes": estilo["pill_classes"],
        "dot_classes": estilo["dot_classes"],
        "card_classes": estilo["card_classes"],
        "estado": None,
        "estado_label": None,
        "estado_classes": "",
        "acao_label": "Abrir",
        "acao_link": link,
        "plano_treino_link": None,
        "agenda_id": None,
        "agenda_editavel": False,
    }


def _item_sessao(sessao: SessaoTreino) -> dict | None:
    equipa = _obter_equipa_sessao(sessao)
    if not equipa:
        return None

    treino_fisico = (getattr(sessao, "tipo_treino", None) or "normal") == "fisico"
    categoria = "jogo" if sessao.e_jogo else ("fisico" if treino_fisico else "treino")
    subtipo = "jogo_sessao" if sessao.e_jogo else ("treino_fisico_sessao" if treino_fisico else "treino_sessao")
    titulo = "Jogo da equipa" if sessao.e_jogo else (
        f"Treino físico {sessao.numero_treino}" if (getattr(sessao, "tipo_treino", None) or "normal") == "fisico" and sessao.numero_treino else
        "Treino físico" if (getattr(sessao, "tipo_treino", None) or "normal") == "fisico" else
        f"Treino {sessao.numero_treino}" if sessao.numero_treino else "Treino"
    )
    detalhe = None
    if sessao.reflexao:
        detalhe = sessao.reflexao.splitlines()[0]
    item = _criar_item_base(
        item_id=f"sessao-{sessao.id}",
        categoria=categoria,
        subtipo=subtipo,
        titulo=titulo,
        data_item=sessao.data,
        hora_inicio=sessao.hora_inicio,
        hora_fim=sessao.hora_fim,
        local=sessao.local,
        equipa_nome=equipa.nome,
        equipa_escalao=equipa.escalao.value if equipa.escalao else None,
        origem_label="Planeamento da equipa" if sessao.origem != "planeamento_global" else "Planeamento global",
        detalhe=detalhe,
        link=f"/treino/sessoes/{sessao.id}",
    )
    estado = normalizar_estado_sessao(getattr(sessao, "estado", None))
    estado_visual = estado_sessao_visual(estado)
    item.update({
        "sessao_id": sessao.id,
        "plano_treino_link": f"/treino/sessoes/{sessao.id}" if not sessao.e_jogo else None,
        "microciclo_id": sessao.microciclo_id,
        "numero_treino": sessao.numero_treino,
        "volume_minutos": sessao.volume_minutos,
        "intensidade_rpe": sessao.intensidade_rpe,
        "e_jogo": sessao.e_jogo,
        "estado": estado,
        "estado_label": estado_visual["label"],
        "estado_classes": estado_visual["classes"],
        "acao_label": proxima_acao_sessao(estado),
        "acao_link": (
            f"/assiduidade/sessoes/{sessao.id}"
            if estado == "executada"
            else f"/treino/sessoes/{sessao.id}"
        ),
    })
    evento_agenda = getattr(sessao, "evento_planeamento_clube", None)
    if evento_agenda:
        metadados = metadados_tipo_agenda(evento_agenda.tipo)
        item.update({
            "titulo": evento_agenda.titulo,
            "badge": metadados["label"],
            "agenda_id": evento_agenda.id,
            "agenda_editavel": True,
            "agenda_tipo": evento_agenda.tipo.value,
            "agenda_titulo": evento_agenda.titulo,
            "agenda_descricao": evento_agenda.descricao or "",
            "agenda_equipa_id": evento_agenda.equipa_id or "",
            "agenda_espaco_id": evento_agenda.espaco_id or "",
            "agenda_macrociclo_id": evento_agenda.macrociclo_id or "",
            "agenda_mesociclo_id": evento_agenda.mesociclo_id or "",
            "agenda_microciclo_id": evento_agenda.microciclo_id or "",
            "agenda_serie_id": evento_agenda.serie_id or "",
            "agenda_data_fim": evento_agenda.data_fim or "",
            "agenda_recorrencia": evento_agenda.recorrencia_frequencia or "unica",
        })
    return item


def apresentar_treinos_por_perfil(itens: list[dict], perfil: str | None) -> list[dict]:
    """Mantém o treino simples para técnicos e identificável na visão global."""
    for item in itens:
        if item.get("categoria") not in {"treino", "fisico"}:
            continue
        nome_treino = "Treino físico" if item.get("categoria") == "fisico" else "Treino"
        if item.get("numero_treino"):
            nome_treino = f"{nome_treino} {item['numero_treino']}"
        if perfil in {"administrador", "coordenador", "superadministrador"} and item.get("equipa_nome"):
            escalao = item.get("equipa_escalao")
            sufixo = f" ({escalao})" if escalao else ""
            item["titulo"] = f"{nome_treino} de {item['equipa_nome']}{sufixo}"
        else:
            local = item.get("local")
            item["titulo"] = f"{nome_treino} ({local})" if local and local != "Local por definir" else nome_treino
    return itens


def _item_jogo(jogo: Jogo) -> dict:
    titulo = f"vs {jogo.adversario}" if jogo.adversario else "Jogo oficial"
    detalhe = jogo.competicao or ("Casa" if jogo.em_casa else "Fora")
    return _criar_item_base(
        item_id=f"jogo-{jogo.id}",
        categoria="jogo",
        subtipo="jogo_oficial",
        titulo=titulo,
        data_item=jogo.data,
        hora_inicio=jogo.hora,
        hora_fim=None,
        local=jogo.local,
        equipa_nome=jogo.equipa.nome if jogo.equipa else None,
        equipa_escalao=jogo.equipa.escalao.value if jogo.equipa and jogo.equipa.escalao else None,
        origem_label="Calendario de jogos",
        detalhe=detalhe,
        link=f"/jogos/{jogo.id}",
    )


def _item_atividade(atividade: Atividade) -> dict:
    detalhe = atividade.tipo or atividade.descricao or atividade.observacoes
    return _criar_item_base(
        item_id=f"atividade-{atividade.id}",
        categoria="atividade",
        subtipo="atividade_global",
        titulo=atividade.titulo,
        data_item=atividade.data,
        hora_inicio=None,
        hora_fim=None,
        local=atividade.local,
        equipa_nome=None,
        equipa_escalao=None,
        origem_label="Atividade global",
        detalhe=detalhe,
        link="/atividades",
    )


def _item_evento(evento: EventoPlaneamentoClube, equipa_id: int | None = None) -> dict:
    metadados = metadados_tipo_agenda(evento.tipo)
    categoria = metadados["categoria"]

    detalhe = evento.descricao or evento.observacoes or metadados["label"]

    equipa_nome = None
    equipa_escalao = None
    if evento.aplica_a_todas_equipas:
        equipa_nome = "Todas as equipas"
    elif evento.equipa:
        equipa_nome = evento.equipa.nome
        equipa_escalao = evento.equipa.escalao.value if evento.equipa.escalao else None
    elif evento.equipas:
        equipa_nome = ", ".join(equipa.nome for equipa in evento.equipas[:2])
        if len(evento.equipas) > 2:
            equipa_nome += f" +{len(evento.equipas) - 2}"

    equipa_para_plano = equipa_id or evento.equipa_id
    link = f"/planeamento-clube/eventos/{evento.id}"
    if equipa_para_plano and evento.tipo in TIPOS_EVENTO_TREINO:
        link = f"/agenda/atividades/{evento.id}/plano?equipa_id={equipa_para_plano}"

    item = _criar_item_base(
        item_id=f"evento-{evento.id}",
        categoria=categoria,
        subtipo=f"evento_{evento.tipo.value}",
        titulo=evento.titulo,
        data_item=evento.data,
        hora_inicio=evento.hora_inicio,
        hora_fim=evento.hora_fim,
        local=evento.espaco.nome if evento.espaco else None,
        equipa_nome=equipa_nome,
        equipa_escalao=equipa_escalao,
        origem_label="Planeamento global",
        detalhe=detalhe,
        link=link,
    )
    item.update({
        "badge": metadados["label"],
        "agenda_id": evento.id,
        "agenda_editavel": True,
        "agenda_tipo": evento.tipo.value,
        "agenda_titulo": evento.titulo,
        "agenda_descricao": evento.descricao or "",
        "agenda_equipa_id": evento.equipa_id or "",
        "agenda_espaco_id": evento.espaco_id or "",
        "agenda_macrociclo_id": evento.macrociclo_id or "",
        "agenda_mesociclo_id": evento.mesociclo_id or "",
        "agenda_microciclo_id": evento.microciclo_id or "",
        "agenda_serie_id": evento.serie_id or "",
        "agenda_data_fim": evento.data_fim or "",
        "agenda_recorrencia": evento.recorrencia_frequencia or "unica",
        "plano_treino_link": link if evento.tipo in TIPOS_EVENTO_TREINO and equipa_para_plano else None,
    })
    return item


def _ordenar_itens(itens: list[dict]) -> list[dict]:
    prioridade = {"treino": 0, "jogo": 1, "atividade": 2}
    return sorted(
        itens,
        key=lambda item: (
            item["data"],
            _hora_para_ordenacao(item["hora_inicio"]),
            prioridade.get(item["categoria"], 9),
            item["titulo"].lower(),
            item["id"],
        ),
    )


def _agrupar_itens_por_data(itens: list[dict]) -> dict[date, list[dict]]:
    itens_por_data: dict[date, list[dict]] = defaultdict(list)
    for item in _ordenar_itens(itens):
        itens_por_data[item["data"]].append(item)
    return itens_por_data


def _calcular_estatisticas(itens: list[dict]) -> dict[str, int]:
    outros = {"recuperacao", "operacao", "fisico", "outro"}
    return {
        "total_itens": len(itens),
        "total_treinos": len([item for item in itens if item["categoria"] == "treino"]),
        "total_jogos": len([item for item in itens if item["categoria"] == "jogo"]),
        "total_atividades": len([item for item in itens if item["categoria"] not in {"treino", "jogo"}]),
        "total_outros": len([item for item in itens if item["categoria"] in outros]),
        "dias_com_atividade": len({item["data"] for item in itens}),
    }


def _construir_dias_intervalo(data_inicio: date, data_fim: date, itens: list[dict]) -> list[dict]:
    itens_por_data = _agrupar_itens_por_data(itens)
    dias = []
    cursor = data_inicio
    while cursor <= data_fim:
        itens_dia = itens_por_data.get(cursor, [])
        dias.append({
            "data": cursor,
            "dia": cursor.day,
            "dia_semana": NOMES_DIAS[cursor.weekday()],
            "itens": itens_dia,
            "total_treinos": len([item for item in itens_dia if item["categoria"] == "treino"]),
            "total_jogos": len([item for item in itens_dia if item["categoria"] == "jogo"]),
            "total_atividades": len([item for item in itens_dia if item["categoria"] not in {"treino", "jogo"}]),
        })
        cursor += timedelta(days=1)
    return dias


def _construir_semanas_intervalo(data_inicio: date, data_fim: date, itens: list[dict]) -> list[list[dict]]:
    itens_por_data = _agrupar_itens_por_data(itens)
    inicio_grade = data_inicio - timedelta(days=data_inicio.weekday())
    fim_grade = data_fim + timedelta(days=6 - data_fim.weekday())

    semanas = []
    cursor = inicio_grade
    while cursor <= fim_grade:
        semana = []
        for offset in range(7):
            dia = cursor + timedelta(days=offset)
            itens_dia = itens_por_data.get(dia, [])
            semana.append({
                "data": dia,
                "dia": dia.day,
                "nome_semana": NOMES_DIAS[dia.weekday()],
                "no_periodo": data_inicio <= dia <= data_fim,
                "itens": itens_dia,
                "total_treinos": len([item for item in itens_dia if item["categoria"] == "treino"]),
                "total_jogos": len([item for item in itens_dia if item["categoria"] == "jogo"]),
                "total_atividades": len([item for item in itens_dia if item["categoria"] not in {"treino", "jogo"}]),
            })
        semanas.append(semana)
        cursor += timedelta(days=7)
    return semanas


def _construir_meses_intervalo(data_inicio: date, data_fim: date, itens: list[dict]) -> list[dict]:
    itens_por_data = _agrupar_itens_por_data(itens)
    meses = []

    cursor = date(data_inicio.year, data_inicio.month, 1)
    limite = date(data_fim.year, data_fim.month, 1)

    while cursor <= limite:
        semanas = []
        total_treinos = 0
        total_jogos = 0
        total_atividades = 0

        for semana in calendar.Calendar(firstweekday=0).monthdatescalendar(cursor.year, cursor.month):
            dias_semana = []
            for dia in semana:
                itens_dia = itens_por_data.get(dia, [])
                if dia.month == cursor.month:
                    total_treinos += len([item for item in itens_dia if item["categoria"] == "treino"])
                    total_jogos += len([item for item in itens_dia if item["categoria"] == "jogo"])
                    total_atividades += len([item for item in itens_dia if item["categoria"] not in {"treino", "jogo"}])
                dias_semana.append({
                    "data": dia,
                    "dia": dia.day,
                    "nome_semana": NOMES_DIAS[dia.weekday()],
                    "do_mes_atual": dia.month == cursor.month,
                    "no_periodo": data_inicio <= dia <= data_fim,
                    "itens": itens_dia,
                })
            semanas.append(dias_semana)

        meses.append({
            "ano": cursor.year,
            "mes": cursor.month,
            "nome_mes": NOMES_MESES[cursor.month],
            "label": f"{NOMES_MESES[cursor.month]} {cursor.year}",
            "semanas": semanas,
            "estatisticas": {
                "treinos": total_treinos,
                "jogos": total_jogos,
                "atividades": total_atividades,
                "itens": total_treinos + total_jogos + total_atividades,
            },
        })

        if cursor.month == 12:
            cursor = date(cursor.year + 1, 1, 1)
        else:
            cursor = date(cursor.year, cursor.month + 1, 1)

    return meses


def _listar_sessoes_intervalo(
    db: Session,
    data_inicio: date,
    data_fim: date,
    equipa_id: int | None = None,
) -> list[SessaoTreino]:
    query = db.query(SessaoTreino).join(Microciclo).join(Mesociclo).join(Macrociclo).filter(
        SessaoTreino.data >= data_inicio,
        SessaoTreino.data <= data_fim,
    )
    if equipa_id:
        query = query.filter(Macrociclo.equipa_id == equipa_id)
    return query.order_by(SessaoTreino.data.asc(), SessaoTreino.id.asc()).all()


def _listar_jogos_intervalo(
    db: Session,
    data_inicio: date,
    data_fim: date,
    equipa_id: int | None = None,
) -> list[Jogo]:
    query = db.query(Jogo).filter(
        Jogo.data >= data_inicio,
        Jogo.data <= data_fim,
    )
    if equipa_id:
        query = query.filter(Jogo.equipa_id == equipa_id)
    return query.order_by(Jogo.data.asc(), Jogo.hora.asc(), Jogo.id.asc()).all()


def _listar_atividades_intervalo(db: Session, data_inicio: date, data_fim: date) -> list[Atividade]:
    return db.query(Atividade).filter(
        Atividade.data >= data_inicio,
        Atividade.data <= data_fim,
    ).order_by(Atividade.data.asc(), Atividade.id.asc()).all()


def _listar_eventos_intervalo(
    db: Session,
    data_inicio: date,
    data_fim: date,
    equipa_id: int | None = None,
) -> list[EventoPlaneamentoClube]:
    eventos = db.query(EventoPlaneamentoClube).filter(
        EventoPlaneamentoClube.ativo.is_(True),
        EventoPlaneamentoClube.data >= data_inicio,
        EventoPlaneamentoClube.data <= data_fim,
    ).order_by(
        EventoPlaneamentoClube.data.asc(),
        EventoPlaneamentoClube.hora_inicio.asc(),
        EventoPlaneamentoClube.id.asc(),
    ).all()
    if not equipa_id:
        return eventos
    return [evento for evento in eventos if _evento_visivel_para_equipa(evento, equipa_id)]


def _construir_itens_integrados(
    db: Session,
    data_inicio: date,
    data_fim: date,
    equipa_id: int | None = None,
) -> list[dict]:
    sessoes = [sessao for sessao in _listar_sessoes_intervalo(db, data_inicio, data_fim, equipa_id) if sessao.ativa]
    jogos = _listar_jogos_intervalo(db, data_inicio, data_fim, equipa_id)
    atividades = _listar_atividades_intervalo(db, data_inicio, data_fim)
    eventos = _listar_eventos_intervalo(db, data_inicio, data_fim, equipa_id)

    itens = []
    eventos_com_sessao = {
        sessao.evento_planeamento_clube_id
        for sessao in sessoes
        if sessao.evento_planeamento_clube_id
    }
    jogo_ids_com_evento = {evento.jogo_id for evento in eventos if evento.jogo_id}
    atividade_ids_com_evento = {evento.atividade_id for evento in eventos if evento.atividade_id}
    jogo_ids_representados = {
        sessao.evento_planeamento_clube.jogo_id
        for sessao in sessoes
        if sessao.e_jogo and getattr(sessao, "evento_planeamento_clube", None) and sessao.evento_planeamento_clube.jogo_id
    }
    datas_jogo_representadas = {sessao.data for sessao in sessoes if sessao.e_jogo}

    for sessao in sessoes:
        item = _item_sessao(sessao)
        if item:
            itens.append(item)

    for jogo in jogos:
        if jogo.id in jogo_ids_representados:
            continue
        if jogo.id in jogo_ids_com_evento:
            continue
        if jogo.data in datas_jogo_representadas:
            continue
        itens.append(_item_jogo(jogo))

    for atividade in atividades:
        if atividade.id in atividade_ids_com_evento:
            continue
        itens.append(_item_atividade(atividade))

    for evento in eventos:
        if evento.tipo in TIPOS_EVENTO_SESSAO and evento.id in eventos_com_sessao:
            continue
        if evento.tipo == TipoEventoPlaneamentoClubeEnum.jogo and evento.jogo_id and evento.jogo_id in jogo_ids_representados:
            continue
        itens.append(_item_evento(evento, equipa_id=equipa_id))

    return _ordenar_itens(itens)


def _construir_resumo_equipas(db: Session, data_inicio: date, data_fim: date) -> list[dict]:
    equipas = db.query(Equipa).order_by(Equipa.nome.asc()).all()
    resumo = []

    for equipa in equipas:
        total_macros = db.query(Macrociclo).filter(Macrociclo.equipa_id == equipa.id).count()
        total_meso = db.query(Mesociclo).join(Macrociclo).filter(
            Macrociclo.equipa_id == equipa.id,
            Mesociclo.data_inicio <= data_fim,
            Mesociclo.data_fim >= data_inicio,
        ).count()
        total_micro = db.query(Microciclo).join(Mesociclo).join(Macrociclo).filter(
            Macrociclo.equipa_id == equipa.id,
            Microciclo.data_inicio <= data_fim,
            Microciclo.data_fim >= data_inicio,
        ).count()
        total_treinos = db.query(SessaoTreino).join(Microciclo).join(Mesociclo).join(Macrociclo).filter(
            Macrociclo.equipa_id == equipa.id,
            SessaoTreino.ativa == True,
            SessaoTreino.e_jogo == False,
            SessaoTreino.data >= data_inicio,
            SessaoTreino.data <= data_fim,
        ).count()
        total_jogos = db.query(Jogo).filter(
            Jogo.equipa_id == equipa.id,
            Jogo.data >= data_inicio,
            Jogo.data <= data_fim,
        ).count()
        resumo.append({
            "equipa": equipa,
            "total_macros": total_macros,
            "total_mesos": total_meso,
            "total_micros": total_micro,
            "total_treinos": total_treinos,
            "total_jogos": total_jogos,
        })

    return resumo


def obter_dashboard_planeamento_intervalo(
    db: Session,
    data_inicio: date,
    data_fim: date,
    equipa_id: int | None = None,
) -> dict:
    itens = _construir_itens_integrados(db, data_inicio, data_fim, equipa_id)
    estatisticas = _calcular_estatisticas(itens)
    dias = _construir_dias_intervalo(data_inicio, data_fim, itens)
    semanas = _construir_semanas_intervalo(data_inicio, data_fim, itens)
    meses = _construir_meses_intervalo(data_inicio, data_fim, itens)

    return {
        "periodo": {
            "inicio": data_inicio,
            "fim": data_fim,
            "label": _label_periodo(data_inicio, data_fim),
        },
        "itens": itens,
        "itens_recentes": itens[:10],
        "estatisticas": estatisticas,
        "dias": dias,
        "semanas": semanas,
        "meses": meses,
    }


def obter_dashboard_planeamento_equipa(
    db: Session,
    equipa_id: int,
    data_inicio: date,
    data_fim: date,
) -> dict:
    return obter_dashboard_planeamento_intervalo(db, data_inicio, data_fim, equipa_id=equipa_id)


def obter_dashboard_planeamento_anual(
    db: Session,
    data_inicio: date,
    data_fim: date,
) -> dict:
    dashboard = obter_dashboard_planeamento_intervalo(db, data_inicio, data_fim)
    dashboard["resumo_equipas"] = _construir_resumo_equipas(db, data_inicio, data_fim)
    dashboard["estatisticas"]["total_equipas"] = len(dashboard["resumo_equipas"])
    return dashboard

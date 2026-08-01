"""Contrato comum para os itens apresentados nas agendas de planeamento."""

from datetime import date

from sqlalchemy.orm import Session

from models.planeamento_clube import EventoPlaneamentoClube, TipoEventoPlaneamentoClubeEnum


TIPOS_AGENDA = {
    TipoEventoPlaneamentoClubeEnum.treino_equipa.value: {
        "label": "Treino",
        "categoria": "treino",
        "cor": "emerald",
    },
    TipoEventoPlaneamentoClubeEnum.treino_individual.value: {
        "label": "Treino individual",
        "categoria": "treino",
        "cor": "emerald",
    },
    TipoEventoPlaneamentoClubeEnum.jogo.value: {
        "label": "Jogo",
        "categoria": "jogo",
        "cor": "rose",
    },
    TipoEventoPlaneamentoClubeEnum.atividade_extra.value: {
        "label": "Atividade",
        "categoria": "atividade",
        "cor": "amber",
    },
    TipoEventoPlaneamentoClubeEnum.evento_clube.value: {
        "label": "Atividade do clube",
        "categoria": "atividade",
        "cor": "amber",
    },
    TipoEventoPlaneamentoClubeEnum.folga.value: {
        "label": "Folga",
        "categoria": "recuperacao",
        "cor": "sky",
    },
    TipoEventoPlaneamentoClubeEnum.torneio.value: {
        "label": "Torneio",
        "categoria": "jogo",
        "cor": "red",
    },
    TipoEventoPlaneamentoClubeEnum.viagem.value: {
        "label": "Viagem",
        "categoria": "operacao",
        "cor": "violet",
    },
    TipoEventoPlaneamentoClubeEnum.teste_fisico.value: {
        "label": "Teste físico",
        "categoria": "fisico",
        "cor": "indigo",
    },
    TipoEventoPlaneamentoClubeEnum.outro.value: {
        "label": "Outro",
        "categoria": "outro",
        "cor": "slate",
    },
}


def valor_tipo_agenda(tipo) -> str:
    """Converte enum ou texto no valor estável usado nos formulários."""
    return getattr(tipo, "value", tipo or TipoEventoPlaneamentoClubeEnum.outro.value)


def metadados_tipo_agenda(tipo) -> dict[str, str]:
    """Devolve label/categoria/cor para qualquer tipo, incluindo dados antigos."""
    valor = valor_tipo_agenda(tipo)
    return dict(TIPOS_AGENDA.get(valor, TIPOS_AGENDA[TipoEventoPlaneamentoClubeEnum.outro.value]))


def tipos_agenda_formulario() -> list[dict[str, str]]:
    """Lista de tipos na ordem adequada para os formulários de criação rápida."""
    return [
        {"value": valor, **dados}
        for valor, dados in TIPOS_AGENDA.items()
    ]


def intervalo_sobreposto(
    data_a: date,
    inicio_a: str | None,
    fim_a: str | None,
    data_b: date,
    inicio_b: str | None,
    fim_b: str | None,
) -> bool:
    """Testa conflito de agenda; eventos sem hora ocupam o dia inteiro."""
    if data_a != data_b:
        return False
    if not inicio_a or not inicio_b:
        return True
    fim_a = fim_a or inicio_a
    fim_b = fim_b or inicio_b
    return inicio_a < fim_b and inicio_b < fim_a


def eventos_agenda_contexto(
    db: Session,
    data_inicio: date,
    data_fim: date,
    *,
    equipa_id: int | None = None,
    macrociclo_id: int | None = None,
    mesociclo_id: int | None = None,
    microciclo_id: int | None = None,
) -> list[EventoPlaneamentoClube]:
    """Obtém eventos comuns por intervalo e contexto de planeamento."""
    query = db.query(EventoPlaneamentoClube).filter(
        EventoPlaneamentoClube.ativo.is_(True),
        EventoPlaneamentoClube.data >= data_inicio,
        EventoPlaneamentoClube.data <= data_fim,
    )
    if macrociclo_id:
        query = query.filter(EventoPlaneamentoClube.macrociclo_id == macrociclo_id)
    if mesociclo_id:
        query = query.filter(EventoPlaneamentoClube.mesociclo_id == mesociclo_id)
    if microciclo_id:
        query = query.filter(EventoPlaneamentoClube.microciclo_id == microciclo_id)
    eventos = query.order_by(
        EventoPlaneamentoClube.data,
        EventoPlaneamentoClube.hora_inicio,
        EventoPlaneamentoClube.id,
    ).all()
    if not equipa_id:
        return eventos
    return [
        evento for evento in eventos
        if evento.aplica_a_todas_equipas
        or evento.equipa_id == equipa_id
        or any(equipa.id == equipa_id for equipa in evento.equipas)
    ]


def conflitos_do_evento(
    db: Session,
    evento: EventoPlaneamentoClube,
) -> list[dict[str, object]]:
    """Identifica conflitos de equipa, treinador e espaço do evento."""
    query = db.query(EventoPlaneamentoClube).filter(
        EventoPlaneamentoClube.id != evento.id,
        EventoPlaneamentoClube.ativo.is_(True),
        EventoPlaneamentoClube.data == evento.data,
    )
    conflitos = []
    for outro in query.order_by(EventoPlaneamentoClube.hora_inicio, EventoPlaneamentoClube.id).all():
        if not intervalo_sobreposto(
            evento.data,
            evento.hora_inicio,
            evento.hora_fim,
            outro.data,
            outro.hora_inicio,
            outro.hora_fim,
        ):
            continue
        mesma_equipa = (
            evento.aplica_a_todas_equipas
            or outro.aplica_a_todas_equipas
            or (evento.equipa_id and evento.equipa_id == outro.equipa_id)
            or bool({item.id for item in evento.equipas} & {item.id for item in outro.equipas})
        )
        if evento.espaco_id and evento.espaco_id == outro.espaco_id:
            conflitos.append({"tipo": "espaco", "evento": outro})
        if evento.treinador_id and evento.treinador_id == outro.treinador_id:
            conflitos.append({"tipo": "treinador", "evento": outro})
        if mesma_equipa:
            conflitos.append({"tipo": "equipa", "evento": outro})
    return conflitos

"""Liga previsões logísticas à agenda sem criar planos técnicos automaticamente."""

from sqlalchemy.orm import Session

from models.atribuicao_espaco_semanal import EstadoAtribuicaoEspacoEnum, TipoOcupacaoEspacoEnum
from models.planeamento import Macrociclo, Mesociclo, Microciclo, SessaoTreino
from models.planeamento_clube import EventoPlaneamentoClube, OrigemEventoPlaneamentoClubeEnum, TipoEventoPlaneamentoClubeEnum
from services.numeracao_planeamento_service import renumerar_treinos_equipa


def _sobrepoe(inicio_a: str, fim_a: str, inicio_b: str | None, fim_b: str | None) -> bool:
    return not inicio_b or not fim_b or (inicio_a < fim_b and fim_a > inicio_b)


def _duracao_minutos(inicio: str, fim: str) -> int:
    inicio_minutos = int(inicio[:2]) * 60 + int(inicio[3:])
    fim_minutos = int(fim[:2]) * 60 + int(fim[3:])
    return max(0, fim_minutos - inicio_minutos)


def _tipo_sessao_da_atribuicao(atribuicao) -> str:
    """Mantém os treinos físicos separados dos treinos normais."""
    return (
        "fisico"
        if atribuicao.tipo_ocupacao == TipoOcupacaoEspacoEnum.treino_fisico
        else "normal"
    )


def _sessao_da_equipa_no_dia(sessoes: list[SessaoTreino], atribuicao, evento) -> SessaoTreino | None:
    """Escolhe a sessão técnica que deve receber a reserva do clube.

    A atribuição logística do clube é a fonte de verdade para local e horário.
    Por isso, uma sessão do treinador é encontrada pela equipa, data e tipo de
    treino, mesmo que ainda não tenha horário/local ou esteja marcada noutra hora.
    """
    tipo_treino = _tipo_sessao_da_atribuicao(atribuicao)
    candidatas = [
        sessao for sessao in sessoes
        if (sessao.tipo_treino or "normal") == tipo_treino
    ]
    if not candidatas:
        return None

    def prioridade(sessao: SessaoTreino) -> tuple:
        return (
            # Uma sessão já ligada à mesma previsão é sempre a mais segura.
            0 if sessao.evento_planeamento_clube_id == evento.id else 1,
            # Depois, preferir uma sessão técnica sem outra ligação administrativa.
            0 if not sessao.evento_planeamento_clube_id else 1,
            # Sessões sem horário são a correspondência mais explícita a completar.
            0 if not sessao.hora_inicio and not sessao.hora_fim else 1,
            sessao.hora_inicio or "99:99",
            sessao.id,
        )

    return min(candidatas, key=prioridade)


def sincronizar_atribuicao_com_agenda(db: Session, atribuicao) -> str:
    """Publica a previsão na agenda e sobrepõe local/horário na sessão do dia.

    A previsão é um EventoPlaneamentoClube; não cria uma SessaoTreino. Se o
    treinador já planeou a sessão para a mesma data, a reserva do clube atualiza
    automaticamente apenas o local e o horário, independentemente dos valores
    que o treinador tenha definido antes.
    """
    if (
        atribuicao.estado != EstadoAtribuicaoEspacoEnum.publicado
        or not atribuicao.equipa_id
        or atribuicao.tipo_ocupacao not in {
            TipoOcupacaoEspacoEnum.treino_equipa,
            TipoOcupacaoEspacoEnum.treino_fisico,
            TipoOcupacaoEspacoEnum.treino_individual,
        }
    ):
        return "A reserva ficou registada sem criar previsão de treino."

    tipo_evento = (
        TipoEventoPlaneamentoClubeEnum.treino_fisico
        if atribuicao.tipo_ocupacao == TipoOcupacaoEspacoEnum.treino_fisico
        else TipoEventoPlaneamentoClubeEnum.treino_individual
        if atribuicao.tipo_ocupacao == TipoOcupacaoEspacoEnum.treino_individual
        else TipoEventoPlaneamentoClubeEnum.treino_equipa
    )
    evento = atribuicao.evento
    if not evento:
        eventos = db.query(EventoPlaneamentoClube).filter(
            EventoPlaneamentoClube.equipa_id == atribuicao.equipa_id,
            EventoPlaneamentoClube.data == atribuicao.data,
            EventoPlaneamentoClube.tipo == tipo_evento,
            EventoPlaneamentoClube.ativo.is_(True),
        ).order_by(EventoPlaneamentoClube.id).all()
        evento = next(
            (item for item in eventos if item.plano_semanal_id == atribuicao.plano_semanal_id),
            eventos[0] if eventos else None,
        )

    if not evento:
        evento = EventoPlaneamentoClube(
            clube_id=atribuicao.clube_id,
            tipo=tipo_evento,
            titulo=(
                "Treino físico"
                if atribuicao.tipo_ocupacao == TipoOcupacaoEspacoEnum.treino_fisico
                else "Treino"
            ),
            descricao="Horário e espaço definidos para a equipa.",
            data=atribuicao.data,
            hora_inicio=atribuicao.hora_inicio,
            hora_fim=atribuicao.hora_fim,
            plano_semanal_id=atribuicao.plano_semanal_id,
            equipa_id=atribuicao.equipa_id,
            treinador_id=atribuicao.treinador_id,
            espaco_id=atribuicao.espaco_id,
            origem=OrigemEventoPlaneamentoClubeEnum.manual,
        )
        db.add(evento)
        db.flush()
    else:
        # Normaliza também previsões antigas quando voltam a ser publicadas.
        if evento.titulo in {"Treino previsto pelo clube", "Treino", "Treino físico"}:
            evento.titulo = (
                "Treino físico"
                if atribuicao.tipo_ocupacao == TipoOcupacaoEspacoEnum.treino_fisico
                else "Treino"
            )
        evento.espaco_id = atribuicao.espaco_id
        evento.treinador_id = atribuicao.treinador_id
        evento.plano_semanal_id = atribuicao.plano_semanal_id
        evento.hora_inicio = atribuicao.hora_inicio
        evento.hora_fim = atribuicao.hora_fim
    atribuicao.evento_id = evento.id

    sessoes = db.query(SessaoTreino).join(Microciclo).join(Mesociclo).join(Macrociclo).filter(
        Macrociclo.equipa_id == atribuicao.equipa_id,
        SessaoTreino.data == atribuicao.data,
        SessaoTreino.ativa.is_(True),
        SessaoTreino.e_jogo.is_(False),
    ).all()
    sessao = _sessao_da_equipa_no_dia(sessoes, atribuicao, evento)
    if sessao:
        sessao.tipo_treino = _tipo_sessao_da_atribuicao(atribuicao)
        sessao.local = atribuicao.espaco.nome
        sessao.hora_inicio = atribuicao.hora_inicio
        sessao.hora_fim = atribuicao.hora_fim
        sessao.plano_semanal_clube_id = atribuicao.plano_semanal_id
        sessao.evento_planeamento_clube_id = evento.id
        renumerar_treinos_equipa(db, atribuicao.equipa_id)
        return "Previsão publicada e horário/local atualizados no treino técnico da equipa."
    return "Previsão publicada na agenda da equipa; ainda não existe um treino técnico nesse dia."

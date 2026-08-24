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


def sincronizar_atribuicao_com_agenda(db: Session, atribuicao) -> str:
    """Publica a previsão na agenda e aplica o espaço a uma sessão coincidente.

    A previsão é um EventoPlaneamentoClube; não cria SessaoTreino. Se o treinador
    já tiver criado uma sessão para a mesma hora, apenas completa o respetivo local.
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

    evento = atribuicao.evento
    if not evento:
        evento = db.query(EventoPlaneamentoClube).filter(
            EventoPlaneamentoClube.equipa_id == atribuicao.equipa_id,
            EventoPlaneamentoClube.data == atribuicao.data,
            EventoPlaneamentoClube.tipo.in_([
                TipoEventoPlaneamentoClubeEnum.treino_equipa,
                TipoEventoPlaneamentoClubeEnum.treino_fisico,
                TipoEventoPlaneamentoClubeEnum.treino_individual,
            ]),
            EventoPlaneamentoClube.ativo.is_(True),
        ).all()
        evento = next((item for item in evento if _sobrepoe(
            atribuicao.hora_inicio, atribuicao.hora_fim, item.hora_inicio, item.hora_fim
        )), None)

    if not evento:
        evento = EventoPlaneamentoClube(
            clube_id=atribuicao.clube_id,
            tipo=(
                TipoEventoPlaneamentoClubeEnum.treino_fisico
                if atribuicao.tipo_ocupacao == TipoOcupacaoEspacoEnum.treino_fisico
                else TipoEventoPlaneamentoClubeEnum.treino_individual
                if atribuicao.tipo_ocupacao == TipoOcupacaoEspacoEnum.treino_individual
                else TipoEventoPlaneamentoClubeEnum.treino_equipa
            ),
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

    sessao = db.query(SessaoTreino).join(Microciclo).join(Mesociclo).join(Macrociclo).filter(
        Macrociclo.equipa_id == atribuicao.equipa_id,
        SessaoTreino.data == atribuicao.data,
        SessaoTreino.ativa.is_(True),
        SessaoTreino.e_jogo.is_(False),
    ).all()
    sessao = next((item for item in sessao if _sobrepoe(
        atribuicao.hora_inicio, atribuicao.hora_fim, item.hora_inicio, item.hora_fim
    )), None)
    if sessao:
        sessao.tipo_treino = "fisico" if atribuicao.tipo_ocupacao == TipoOcupacaoEspacoEnum.treino_fisico else "normal"
        sessao.local = atribuicao.espaco.nome
        sessao.hora_inicio = atribuicao.hora_inicio
        sessao.hora_fim = atribuicao.hora_fim
        if sessao.volume_minutos is None:
            sessao.volume_minutos = _duracao_minutos(atribuicao.hora_inicio, atribuicao.hora_fim)
        if sessao.intensidade_rpe is None:
            sessao.intensidade_rpe = 0
        sessao.plano_semanal_clube_id = atribuicao.plano_semanal_id
        sessao.evento_planeamento_clube_id = evento.id
        renumerar_treinos_equipa(db, atribuicao.equipa_id)
        return "Previsão publicada e local aplicado ao treino técnico coincidente."
    return "Previsão publicada na agenda da equipa; ainda não existe um treino técnico coincidente."

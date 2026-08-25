"""Mantém o volume previsto dos treinos alinhado com o respetivo horário."""

from sqlalchemy.orm import Session

from horarios import duracao_minutos
from models.planeamento import SessaoTreino


def atualizar_volume_automatico(sessao: SessaoTreino) -> None:
    """Atualiza o volume de um treino a partir das horas ou deixa-o vazio."""
    if sessao.e_jogo:
        return
    sessao.volume_minutos = duracao_minutos(sessao.hora_inicio, sessao.hora_fim)


def sincronizar_volumes_automaticos(db: Session) -> int:
    """Normaliza sessões existentes após uma atualização da aplicação."""
    alteradas = 0
    sessoes = db.query(SessaoTreino).execution_options(ignorar_clube=True).filter(
        SessaoTreino.e_jogo.is_(False)
    ).all()
    for sessao in sessoes:
        volume = duracao_minutos(sessao.hora_inicio, sessao.hora_fim)
        if sessao.volume_minutos != volume:
            sessao.volume_minutos = volume
            alteradas += 1
    return alteradas

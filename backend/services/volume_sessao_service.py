"""Mantém o volume previsto dos treinos alinhado com o respetivo horário."""

from sqlalchemy.orm import Session

from horarios import duracao_minutos
from models.planeamento import SessaoTreino


def atualizar_volume_automatico(sessao: SessaoTreino) -> None:
    """Atualiza a carga automática: jogos têm sempre RPE 10."""
    if sessao.e_jogo:
        sessao.intensidade_rpe = 10
        return
    sessao.volume_minutos = duracao_minutos(sessao.hora_inicio, sessao.hora_fim)


def sincronizar_volumes_automaticos(db: Session) -> int:
    """Normaliza sessões existentes após uma atualização da aplicação."""
    alteradas = 0
    sessoes = db.query(SessaoTreino).execution_options(ignorar_clube=True).all()
    for sessao in sessoes:
        if sessao.e_jogo:
            if sessao.intensidade_rpe != 10:
                sessao.intensidade_rpe = 10
                alteradas += 1
            continue
        volume = duracao_minutos(sessao.hora_inicio, sessao.hora_fim)
        if sessao.volume_minutos != volume:
            sessao.volume_minutos = volume
            alteradas += 1
    return alteradas

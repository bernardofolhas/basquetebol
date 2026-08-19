"""Regras do calendário logístico semanal, independente das sessões técnicas."""
from datetime import date, timedelta

from sqlalchemy.orm import Session

from models.atribuicao_espaco_semanal import AtribuicaoEspacoSemanal, EstadoAtribuicaoEspacoEnum
from models.espaco_treino import (
    DisponibilidadeEspacoTreino,
    EspacoTreino,
    IndisponibilidadeEspacoTreino,
)
from models.indisponibilidade_treinador import IndisponibilidadeTreinador


def _minutos(hora: str) -> int:
    horas, minutos = map(int, hora.split(":"))
    return horas * 60 + minutos


def _hora(total: int) -> str:
    return f"{total // 60:02d}:{total % 60:02d}"


def _sobrepoe(inicio_a: str, fim_a: str, inicio_b: str, fim_b: str) -> bool:
    return inicio_a < fim_b and fim_a > inicio_b


def obter_bloqueio(
    db: Session,
    espaco_id: int,
    data_slot: date,
    hora_inicio: str,
    hora_fim: str,
):
    bloqueios = db.query(IndisponibilidadeEspacoTreino).filter(
        IndisponibilidadeEspacoTreino.espaco_id == espaco_id,
        IndisponibilidadeEspacoTreino.data_inicio <= data_slot,
        IndisponibilidadeEspacoTreino.data_fim >= data_slot,
    ).all()
    for bloqueio in bloqueios:
        if not bloqueio.hora_inicio or not bloqueio.hora_fim:
            return bloqueio
        if _sobrepoe(hora_inicio, hora_fim, bloqueio.hora_inicio, bloqueio.hora_fim):
            return bloqueio
    return None


def horario_dentro_disponibilidade(
    db: Session,
    espaco_id: int,
    data_slot: date,
    hora_inicio: str,
    hora_fim: str,
) -> bool:
    return db.query(DisponibilidadeEspacoTreino).filter(
        DisponibilidadeEspacoTreino.espaco_id == espaco_id,
        DisponibilidadeEspacoTreino.dia_semana == data_slot.weekday(),
        DisponibilidadeEspacoTreino.ativo.is_(True),
        DisponibilidadeEspacoTreino.hora_inicio <= hora_inicio,
        DisponibilidadeEspacoTreino.hora_fim >= hora_fim,
    ).first() is not None


def horario_corresponde_slot(
    db: Session,
    espaco_id: int,
    data_slot: date,
    hora_inicio: str,
    hora_fim: str,
) -> bool:
    regras = db.query(DisponibilidadeEspacoTreino).filter(
        DisponibilidadeEspacoTreino.espaco_id == espaco_id,
        DisponibilidadeEspacoTreino.dia_semana == data_slot.weekday(),
        DisponibilidadeEspacoTreino.ativo.is_(True),
    ).all()
    for regra in regras:
        cursor = _minutos(regra.hora_inicio)
        limite = _minutos(regra.hora_fim)
        while cursor + regra.duracao_slot_minutos <= limite:
            if _hora(cursor) == hora_inicio and _hora(cursor + regra.duracao_slot_minutos) == hora_fim:
                return True
            cursor += regra.duracao_slot_minutos
    return False


def validar_reserva(
    db: Session,
    *,
    espaco_id: int,
    equipa_id: int | None,
    treinador_id: int | None,
    data_slot: date,
    hora_inicio: str,
    hora_fim: str,
    excluir_id: int | None = None,
) -> list[str]:
    """Valida disponibilidade, bloqueios e sobreposições da reserva."""
    erros = []
    if not horario_corresponde_slot(db, espaco_id, data_slot, hora_inicio, hora_fim):
        erros.append("O horário não corresponde a um slot disponível configurado para o espaço.")
    bloqueio = obter_bloqueio(db, espaco_id, data_slot, hora_inicio, hora_fim)
    if bloqueio:
        erros.append(f"O espaço está indisponível neste período: {bloqueio.motivo or 'bloqueio do clube'}.")

    query = db.query(AtribuicaoEspacoSemanal).filter(
        AtribuicaoEspacoSemanal.data == data_slot,
        AtribuicaoEspacoSemanal.estado != EstadoAtribuicaoEspacoEnum.cancelado,
        AtribuicaoEspacoSemanal.hora_inicio < hora_fim,
        AtribuicaoEspacoSemanal.hora_fim > hora_inicio,
    )
    if excluir_id:
        query = query.filter(AtribuicaoEspacoSemanal.id != excluir_id)
    reservas = query.all()
    if any(item.espaco_id == espaco_id for item in reservas):
        erros.append("O espaço já está ocupado neste horário.")
    if equipa_id and any(item.equipa_id == equipa_id for item in reservas):
        erros.append("A equipa já tem outra atividade neste horário.")
    if treinador_id and any(item.treinador_id == treinador_id for item in reservas):
        erros.append("O treinador já está atribuído a outra equipa neste horário.")
    if treinador_id and db.query(IndisponibilidadeTreinador).filter(
        IndisponibilidadeTreinador.treinador_id == treinador_id,
        IndisponibilidadeTreinador.data == data_slot,
        IndisponibilidadeTreinador.hora_inicio < hora_fim,
        IndisponibilidadeTreinador.hora_fim > hora_inicio,
    ).first():
        erros.append("O treinador indicou indisponibilidade neste horário.")
    return erros


def gerar_grelha_slots(db: Session, semanal) -> dict:
    """Gera slots visuais, incluindo reservas criadas fora de uma disponibilidade."""
    espacos = db.query(EspacoTreino).filter(EspacoTreino.ativo.is_(True)).order_by(EspacoTreino.nome).all()
    reservas = db.query(AtribuicaoEspacoSemanal).filter(
        AtribuicaoEspacoSemanal.plano_semanal_id == semanal.id,
        AtribuicaoEspacoSemanal.estado != EstadoAtribuicaoEspacoEnum.cancelado,
    ).all()
    dias = []
    atual = semanal.data_inicio
    while atual <= semanal.data_fim:
        dia = {"data": atual, "slots": []}
        for espaco in espacos:
            regras = [r for r in espaco.disponibilidades if r.ativo and r.dia_semana == atual.weekday()]
            for regra in regras:
                cursor = _minutos(regra.hora_inicio)
                limite = _minutos(regra.hora_fim)
                while cursor + regra.duracao_slot_minutos <= limite:
                    inicio = _hora(cursor)
                    fim = _hora(cursor + regra.duracao_slot_minutos)
                    bloqueio = obter_bloqueio(db, espaco.id, atual, inicio, fim)
                    dia["slots"].append({
                        "espaco": espaco,
                        "hora_inicio": inicio,
                        "hora_fim": fim,
                        "bloqueio": bloqueio,
                        "atribuicao": next((r for r in reservas if r.espaco_id == espaco.id and r.data == atual and _sobrepoe(inicio, fim, r.hora_inicio, r.hora_fim)), None),
                    })
                    cursor += regra.duracao_slot_minutos

        # Uma reserva pode ter sido criada antes de o horário do espaço existir,
        # ou ter sido autorizada como exceção. Nunca a ocultamos do mapa.
        for reserva in (item for item in reservas if item.data == atual):
            ja_visivel = any(
                slot["espaco"].id == reserva.espaco_id
                and _sobrepoe(slot["hora_inicio"], slot["hora_fim"], reserva.hora_inicio, reserva.hora_fim)
                for slot in dia["slots"]
            )
            if not ja_visivel:
                dia["slots"].append({
                    "espaco": reserva.espaco,
                    "hora_inicio": reserva.hora_inicio,
                    "hora_fim": reserva.hora_fim,
                    "bloqueio": obter_bloqueio(db, reserva.espaco_id, atual, reserva.hora_inicio, reserva.hora_fim),
                    "atribuicao": reserva,
                    "fora_disponibilidade": True,
                })
        dia["slots"].sort(key=lambda slot: (slot["hora_inicio"], slot["espaco"].nome.casefold()))
        dias.append(dia)
        atual += timedelta(days=1)
    return {"dias": dias, "espacos": espacos, "total": sum(len(dia["slots"]) for dia in dias)}


def obter_previsao_equipa(db: Session, equipa_id: int, inicio: date, fim: date) -> list:
    return db.query(AtribuicaoEspacoSemanal).filter(
        AtribuicaoEspacoSemanal.equipa_id == equipa_id,
        AtribuicaoEspacoSemanal.data >= inicio,
        AtribuicaoEspacoSemanal.data <= fim,
        AtribuicaoEspacoSemanal.estado == EstadoAtribuicaoEspacoEnum.publicado,
    ).order_by(AtribuicaoEspacoSemanal.data, AtribuicaoEspacoSemanal.hora_inicio).all()


def validar_local_sessao(db: Session, sessao, equipa_id: int) -> dict:
    """Compara a sessão técnica com a previsão sem bloquear a escolha do treinador."""
    if not sessao.local:
        estado = "sem_local"
        label = "Local ainda não atribuído"
        classes = "border-sky-200 bg-sky-50 text-sky-800"
    else:
        estado = "sem_previsao"
        label = "Sem previsão administrativa"
        classes = "border-amber-200 bg-amber-50 text-amber-800"

    previsoes = obter_previsao_equipa(db, equipa_id, sessao.data, sessao.data)
    previsao = next((item for item in previsoes if (
        not sessao.hora_inicio or not sessao.hora_fim
        or _sobrepoe(sessao.hora_inicio, sessao.hora_fim, item.hora_inicio, item.hora_fim)
    )), None)
    if previsao and sessao.local:
        if previsao.espaco and sessao.local.strip().casefold() == previsao.espaco.nome.strip().casefold():
            estado, label, classes = "confirmado", "Local confirmado", "border-emerald-200 bg-emerald-50 text-emerald-800"
        else:
            estado, label, classes = "diferente", "Local diferente do previsto", "border-amber-200 bg-amber-50 text-amber-800"
    return {"estado": estado, "label": label, "classes": classes, "previsao": previsao}

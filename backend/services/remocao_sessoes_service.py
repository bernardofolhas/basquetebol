"""Remoção definitiva de sessões e limpeza de registos operacionais órfãos."""

from sqlalchemy import or_
from sqlalchemy.orm import Session

from models.planeamento import Macrociclo, Mesociclo, Microciclo, SessaoTreino
from services.numeracao_planeamento_service import renumerar_treinos_equipa


ORIGENS_GERADAS_PELO_CLUBE = ("planeamento_global", "planeamento_integrado")


def obter_equipa_id_sessao(sessao: SessaoTreino) -> int | None:
    if not sessao.microciclo or not sessao.microciclo.mesociclo or not sessao.microciclo.mesociclo.macrociclo:
        return None
    return sessao.microciclo.mesociclo.macrociclo.equipa_id


def eliminar_sessoes_treino(db: Session, sessoes: list[SessaoTreino]) -> int:
    """Apaga sessões e dependências, renumerando as equipas afetadas."""
    unicas = {sessao.id: sessao for sessao in sessoes if sessao and sessao.id is not None}
    equipas_ids = {
        equipa_id
        for sessao in unicas.values()
        if (equipa_id := obter_equipa_id_sessao(sessao)) is not None
    }
    for sessao in unicas.values():
        if sessao not in db.deleted:
            db.delete(sessao)
    if unicas:
        db.flush()
    for equipa_id in equipas_ids:
        renumerar_treinos_equipa(db, equipa_id)
    return len(unicas)


def limpar_sessoes_geradas_orfas(db: Session) -> int:
    """Remove sessões geradas cujo plano semanal e evento já desapareceram."""
    sessoes = db.query(SessaoTreino).execution_options(ignorar_clube=True).filter(
        SessaoTreino.plano_semanal_clube_id.is_(None),
        SessaoTreino.evento_planeamento_clube_id.is_(None),
        SessaoTreino.e_jogo.is_(False),
        or_(
            SessaoTreino.origem.in_(ORIGENS_GERADAS_PELO_CLUBE),
            SessaoTreino.reflexao.like("Evento global:%"),
        ),
    ).all()
    return eliminar_sessoes_treino(db, sessoes)

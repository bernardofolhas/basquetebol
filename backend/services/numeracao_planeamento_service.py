"""Mantém a numeração dos ciclos coerente com a cronologia do planeamento."""

from sqlalchemy.orm import Session

from models.planeamento import Macrociclo, Mesociclo, Microciclo, SessaoTreino


def _renumerar(ciclos: list) -> None:
    """A data de início define a ordem; fim e id tornam empates determinísticos."""
    for numero, ciclo in enumerate(ciclos, start=1):
        ciclo.numero = numero


def renumerar_macrociclos(db: Session, equipa_id: int, planeamento_anual_equipa_id: int | None) -> None:
    consulta = db.query(Macrociclo).filter(Macrociclo.equipa_id == equipa_id)
    if planeamento_anual_equipa_id is None:
        consulta = consulta.filter(Macrociclo.planeamento_anual_equipa_id.is_(None))
    else:
        consulta = consulta.filter(Macrociclo.planeamento_anual_equipa_id == planeamento_anual_equipa_id)
    _renumerar(consulta.order_by(Macrociclo.data_inicio, Macrociclo.data_fim, Macrociclo.id).all())


def renumerar_mesociclos(db: Session, macrociclo_id: int) -> None:
    ciclos = db.query(Mesociclo).filter(
        Mesociclo.macrociclo_id == macrociclo_id,
    ).order_by(Mesociclo.data_inicio, Mesociclo.data_fim, Mesociclo.id).all()
    _renumerar(ciclos)


def renumerar_microciclos(db: Session, mesociclo_id: int) -> None:
    ciclos = db.query(Microciclo).filter(
        Microciclo.mesociclo_id == mesociclo_id,
    ).order_by(Microciclo.data_inicio, Microciclo.data_fim, Microciclo.id).all()
    _renumerar(ciclos)


def renumerar_treinos_equipa(db: Session, equipa_id: int) -> None:
    """Numera separadamente treinos normais e físicos em cada microciclo."""
    sessoes = db.query(SessaoTreino).execution_options(ignorar_clube=True).join(Microciclo).join(Mesociclo).join(Macrociclo).filter(
        Macrociclo.equipa_id == equipa_id,
        SessaoTreino.e_jogo.is_(False),
        SessaoTreino.ativa.is_(True),
    ).order_by(
        SessaoTreino.microciclo_id,
        SessaoTreino.data,
        SessaoTreino.hora_inicio,
        SessaoTreino.id,
    ).all()
    grupos: dict[tuple[int, str], list[SessaoTreino]] = {}
    for sessao in sessoes:
        tipo_treino = getattr(sessao, "tipo_treino", None) or "normal"
        grupos.setdefault((sessao.microciclo_id, tipo_treino), []).append(sessao)
    for grupo in grupos.values():
        for numero, sessao in enumerate(grupo, start=1):
            sessao.numero_treino = numero


def renumerar_todos_os_ciclos(db: Session) -> None:
    """Alinha também os ciclos existentes quando a aplicação arranca."""
    # O arranque é também o ponto seguro para remover sessões geradas cujo
    # plano semanal e evento de origem já foram eliminados.
    from services.remocao_sessoes_service import limpar_sessoes_geradas_orfas

    limpar_sessoes_geradas_orfas(db)
    macrociclos = db.query(Macrociclo).execution_options(ignorar_clube=True).order_by(
        Macrociclo.equipa_id, Macrociclo.planeamento_anual_equipa_id,
        Macrociclo.data_inicio, Macrociclo.data_fim, Macrociclo.id,
    ).all()
    grupos_macro: dict[tuple[int, int | None], list[Macrociclo]] = {}
    for macro in macrociclos:
        grupos_macro.setdefault((macro.equipa_id, macro.planeamento_anual_equipa_id), []).append(macro)
    for grupo in grupos_macro.values():
        _renumerar(grupo)

    mesociclos = db.query(Mesociclo).execution_options(ignorar_clube=True).order_by(
        Mesociclo.macrociclo_id, Mesociclo.data_inicio, Mesociclo.data_fim, Mesociclo.id,
    ).all()
    grupos_meso: dict[int, list[Mesociclo]] = {}
    for meso in mesociclos:
        grupos_meso.setdefault(meso.macrociclo_id, []).append(meso)
    for grupo in grupos_meso.values():
        _renumerar(grupo)

    microciclos = db.query(Microciclo).execution_options(ignorar_clube=True).order_by(
        Microciclo.mesociclo_id, Microciclo.data_inicio, Microciclo.data_fim, Microciclo.id,
    ).all()
    grupos_micro: dict[int, list[Microciclo]] = {}
    for micro in microciclos:
        grupos_micro.setdefault(micro.mesociclo_id, []).append(micro)
    for grupo in grupos_micro.values():
        _renumerar(grupo)

    equipas_ids = {
        equipa_id for (equipa_id,) in db.query(Macrociclo.equipa_id).execution_options(
            ignorar_clube=True
        ).distinct().all()
    }
    for equipa_id in equipas_ids:
        renumerar_treinos_equipa(db, equipa_id)

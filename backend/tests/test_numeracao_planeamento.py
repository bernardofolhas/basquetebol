from datetime import date
from uuid import uuid4

from database import SessionLocal
from models.clube import Clube
from models.equipa import Equipa, EscalaoEnum, GeneroEnum
from models.planeamento import Macrociclo, Mesociclo, Microciclo, PlaneamentoAnualEquipa, SessaoTreino
from models.planeamento_clube import EventoPlaneamentoClube, TipoEventoPlaneamentoClubeEnum
from routers.planeamento import _integrar_eventos_planeados_no_microciclo
from services.numeracao_planeamento_service import (
    renumerar_macrociclos,
    renumerar_mesociclos,
    renumerar_microciclos,
    renumerar_treinos_equipa,
    renumerar_todos_os_ciclos,
)


def test_ciclos_sao_renumerados_pela_data_de_inicio():
    sufixo = uuid4().hex[:10]
    db = SessionLocal()
    clube = Clube(nome_oficial=f"Clube numeracao {sufixo}", nome_curto="Numeracao", identificador=f"num-{sufixo}")
    db.add(clube)
    db.flush()
    equipa = Equipa(clube_id=clube.id, nome=f"Equipa numeracao {sufixo}", escalao=EscalaoEnum.sub18, genero=GeneroEnum.feminino)
    db.add(equipa)
    db.flush()
    anual = PlaneamentoAnualEquipa(clube_id=clube.id, equipa_id=equipa.id, epoca="2026/2027", titulo="Anual", data_inicio=date(2026, 1, 1), data_fim=date(2026, 12, 31))
    db.add(anual)
    db.flush()
    try:
        macro_tardio = Macrociclo(clube_id=clube.id, equipa_id=equipa.id, planeamento_anual_equipa_id=anual.id, numero=1, data_inicio=date(2026, 7, 1), data_fim=date(2026, 12, 31))
        macro_cedo = Macrociclo(clube_id=clube.id, equipa_id=equipa.id, planeamento_anual_equipa_id=anual.id, numero=9, data_inicio=date(2026, 1, 1), data_fim=date(2026, 6, 30))
        db.add_all([macro_tardio, macro_cedo])
        db.flush()
        renumerar_macrociclos(db, equipa.id, anual.id)

        meso_tardio = Mesociclo(clube_id=clube.id, macrociclo_id=macro_cedo.id, numero=1, data_inicio=date(2026, 3, 1), data_fim=date(2026, 3, 31))
        meso_cedo = Mesociclo(clube_id=clube.id, macrociclo_id=macro_cedo.id, numero=9, data_inicio=date(2026, 1, 1), data_fim=date(2026, 2, 28))
        db.add_all([meso_tardio, meso_cedo])
        db.flush()
        renumerar_mesociclos(db, macro_cedo.id)

        micro_tardio = Microciclo(clube_id=clube.id, mesociclo_id=meso_cedo.id, numero=1, data_inicio=date(2026, 1, 8), data_fim=date(2026, 1, 14))
        micro_cedo = Microciclo(clube_id=clube.id, mesociclo_id=meso_cedo.id, numero=9, data_inicio=date(2026, 1, 1), data_fim=date(2026, 1, 7))
        db.add_all([micro_tardio, micro_cedo])
        db.flush()
        renumerar_microciclos(db, meso_cedo.id)
        sessao_tardia = SessaoTreino(
            clube_id=clube.id, microciclo_id=micro_cedo.id, data=date(2026, 1, 5),
            hora_inicio="20:00", numero_treino=9, e_jogo=False, ativa=True,
        )
        sessao_cedo = SessaoTreino(
            clube_id=clube.id, microciclo_id=micro_cedo.id, data=date(2026, 1, 2),
            hora_inicio="18:00", numero_treino=8, e_jogo=False, ativa=True,
        )
        db.add_all([sessao_tardia, sessao_cedo])
        db.flush()
        renumerar_treinos_equipa(db, equipa.id)
        renumerar_todos_os_ciclos(db)
        db.commit()

        assert (macro_cedo.numero, macro_tardio.numero) == (1, 2)
        assert (meso_cedo.numero, meso_tardio.numero) == (1, 2)
        assert (micro_cedo.numero, micro_tardio.numero) == (1, 2)
        assert (sessao_cedo.numero_treino, sessao_tardia.numero_treino) == (1, 2)
    finally:
        db.rollback()
        db.query(SessaoTreino).execution_options(ignorar_clube=True).filter(SessaoTreino.clube_id == clube.id).delete(synchronize_session=False)
        db.query(Microciclo).execution_options(ignorar_clube=True).filter(Microciclo.clube_id == clube.id).delete(synchronize_session=False)
        db.query(Mesociclo).execution_options(ignorar_clube=True).filter(Mesociclo.clube_id == clube.id).delete(synchronize_session=False)
        db.query(Macrociclo).execution_options(ignorar_clube=True).filter(Macrociclo.clube_id == clube.id).delete(synchronize_session=False)
        db.query(PlaneamentoAnualEquipa).execution_options(ignorar_clube=True).filter(PlaneamentoAnualEquipa.clube_id == clube.id).delete(synchronize_session=False)
        db.query(Equipa).execution_options(ignorar_clube=True).filter(Equipa.id == equipa.id).delete(synchronize_session=False)
        db.query(Clube).filter(Clube.id == clube.id).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_treino_planeado_pelo_treinador_entra_no_microciclo_existente():
    """Um treino criado acima do micro passa a sessão com carga editável."""
    sufixo = uuid4().hex[:10]
    db = SessionLocal()
    clube = Clube(nome_oficial=f"Clube integração {sufixo}", nome_curto="Integração", identificador=f"int-{sufixo}")
    db.add(clube)
    db.flush()
    equipa = Equipa(clube_id=clube.id, nome=f"Equipa integração {sufixo}", escalao=EscalaoEnum.sub18, genero=GeneroEnum.feminino)
    db.add(equipa)
    db.flush()
    anual = PlaneamentoAnualEquipa(
        clube_id=clube.id, equipa_id=equipa.id, epoca="2026/2027", titulo="Anual",
        data_inicio=date(2026, 9, 1), data_fim=date(2027, 6, 30),
    )
    db.add(anual)
    db.flush()
    macro = Macrociclo(
        clube_id=clube.id, equipa_id=equipa.id, planeamento_anual_equipa_id=anual.id,
        numero=1, data_inicio=date(2026, 9, 1), data_fim=date(2026, 10, 31),
    )
    db.add(macro)
    db.flush()
    meso = Mesociclo(
        clube_id=clube.id, macrociclo_id=macro.id, numero=1,
        data_inicio=date(2026, 9, 1), data_fim=date(2026, 9, 30),
    )
    db.add(meso)
    db.flush()
    micro = Microciclo(
        clube_id=clube.id, mesociclo_id=meso.id, numero=1,
        data_inicio=date(2026, 9, 7), data_fim=date(2026, 9, 13),
    )
    db.add(micro)
    db.flush()
    evento = EventoPlaneamentoClube(
        clube_id=clube.id, equipa_id=equipa.id,
        tipo=TipoEventoPlaneamentoClubeEnum.treino_equipa,
        titulo="Treino", data=date(2026, 9, 9), hora_inicio="18:30", hora_fim="20:00",
    )
    db.add(evento)
    db.flush()
    try:
        assert _integrar_eventos_planeados_no_microciclo(db, micro) > 0
        db.flush()
        sessao = db.query(SessaoTreino).filter(
            SessaoTreino.microciclo_id == micro.id,
            SessaoTreino.evento_planeamento_clube_id == evento.id,
        ).one()

        assert sessao.numero_treino == 1
        assert sessao.volume_minutos == 90
        assert sessao.intensidade_rpe is None
        assert evento.microciclo_id == micro.id
    finally:
        db.rollback()
        db.query(EventoPlaneamentoClube).execution_options(ignorar_clube=True).filter(EventoPlaneamentoClube.clube_id == clube.id).delete(synchronize_session=False)
        db.query(SessaoTreino).execution_options(ignorar_clube=True).filter(SessaoTreino.clube_id == clube.id).delete(synchronize_session=False)
        db.query(Microciclo).execution_options(ignorar_clube=True).filter(Microciclo.clube_id == clube.id).delete(synchronize_session=False)
        db.query(Mesociclo).execution_options(ignorar_clube=True).filter(Mesociclo.clube_id == clube.id).delete(synchronize_session=False)
        db.query(Macrociclo).execution_options(ignorar_clube=True).filter(Macrociclo.clube_id == clube.id).delete(synchronize_session=False)
        db.query(PlaneamentoAnualEquipa).execution_options(ignorar_clube=True).filter(PlaneamentoAnualEquipa.clube_id == clube.id).delete(synchronize_session=False)
        db.query(Equipa).execution_options(ignorar_clube=True).filter(Equipa.id == equipa.id).delete(synchronize_session=False)
        db.query(Clube).filter(Clube.id == clube.id).delete(synchronize_session=False)
        db.commit()
        db.close()

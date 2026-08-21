from datetime import date
from uuid import uuid4

from database import SessionLocal
from models.clube import Clube
from models.equipa import Equipa, EscalaoEnum, GeneroEnum
from models.planeamento import Macrociclo, Mesociclo, Microciclo, PlaneamentoAnualEquipa
from services.numeracao_planeamento_service import (
    renumerar_macrociclos,
    renumerar_mesociclos,
    renumerar_microciclos,
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
        renumerar_todos_os_ciclos(db)
        db.commit()

        assert (macro_cedo.numero, macro_tardio.numero) == (1, 2)
        assert (meso_cedo.numero, meso_tardio.numero) == (1, 2)
        assert (micro_cedo.numero, micro_tardio.numero) == (1, 2)
    finally:
        db.rollback()
        db.query(Microciclo).execution_options(ignorar_clube=True).filter(Microciclo.clube_id == clube.id).delete(synchronize_session=False)
        db.query(Mesociclo).execution_options(ignorar_clube=True).filter(Mesociclo.clube_id == clube.id).delete(synchronize_session=False)
        db.query(Macrociclo).execution_options(ignorar_clube=True).filter(Macrociclo.clube_id == clube.id).delete(synchronize_session=False)
        db.query(PlaneamentoAnualEquipa).execution_options(ignorar_clube=True).filter(PlaneamentoAnualEquipa.clube_id == clube.id).delete(synchronize_session=False)
        db.query(Equipa).execution_options(ignorar_clube=True).filter(Equipa.id == equipa.id).delete(synchronize_session=False)
        db.query(Clube).filter(Clube.id == clube.id).delete(synchronize_session=False)
        db.commit()
        db.close()

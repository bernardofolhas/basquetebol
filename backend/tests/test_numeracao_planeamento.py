from datetime import date
from types import SimpleNamespace
from uuid import uuid4

from database import SessionLocal
from models.clube import Clube
from models.equipa import Equipa, EscalaoEnum, GeneroEnum
from models.planeamento import Macrociclo, Mesociclo, Microciclo, PlaneamentoAnualEquipa, SessaoTreino
from models.planeamento_clube import EventoPlaneamentoClube, TipoEventoPlaneamentoClubeEnum
from models.treino import ExercicioPlano, PlanoTreino
from routers.planeamento import _integrar_eventos_planeados_no_microciclo
from routers.planeamento_clube import (
    _eliminar_evento_com_dependencias,
    _remover_sessoes_da_atribuicao,
    _remover_sessoes_do_plano_semanal,
)
from services.remocao_sessoes_service import limpar_sessoes_geradas_orfas
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
        treino_fisico = SessaoTreino(
            clube_id=clube.id, microciclo_id=micro_cedo.id, data=date(2026, 1, 3),
            hora_inicio="18:00", numero_treino=7, tipo_treino="fisico", e_jogo=False, ativa=True,
        )
        db.add_all([sessao_tardia, sessao_cedo, treino_fisico])
        db.flush()
        renumerar_treinos_equipa(db, equipa.id)
        renumerar_todos_os_ciclos(db)
        db.commit()

        assert (macro_cedo.numero, macro_tardio.numero) == (1, 2)
        assert (meso_cedo.numero, meso_tardio.numero) == (1, 2)
        assert (micro_cedo.numero, micro_tardio.numero) == (1, 2)
        assert (sessao_cedo.numero_treino, sessao_tardia.numero_treino) == (1, 2)
        assert treino_fisico.numero_treino == 1
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

        _eliminar_evento_com_dependencias(db, evento)
        db.flush()
        assert db.get(SessaoTreino, sessao.id) is None

        evento_com_ficha = EventoPlaneamentoClube(
            clube_id=clube.id, equipa_id=equipa.id,
            tipo=TipoEventoPlaneamentoClubeEnum.treino_equipa,
            titulo="Treino com ficha", data=date(2026, 9, 10),
        )
        db.add(evento_com_ficha)
        db.flush()
        sessao_com_ficha = SessaoTreino(
            clube_id=clube.id, microciclo_id=micro.id, data=date(2026, 9, 10),
            numero_treino=2, e_jogo=False, ativa=True,
            evento_planeamento_clube_id=evento_com_ficha.id,
        )
        db.add(sessao_com_ficha)
        db.flush()
        plano = PlanoTreino(clube_id=clube.id, sessao_id=sessao_com_ficha.id)
        db.add(plano)
        db.flush()
        db.add(ExercicioPlano(clube_id=clube.id, plano_id=plano.id, ordem=1, nome="Exercício planeado"))
        db.flush()

        sessao_com_ficha_id = sessao_com_ficha.id
        removidas, preservadas = _eliminar_evento_com_dependencias(db, evento_com_ficha)
        assert (removidas, preservadas) == (1, 0)
        assert db.get(SessaoTreino, sessao_com_ficha_id) is None

        # Algumas sessões antigas foram criadas antes de a ligação ao plano semanal
        # ficar persistida. A remoção continua a encontrá-las pela reserva publicada.
        sessao_orfa = SessaoTreino(
            clube_id=clube.id,
            microciclo_id=micro.id,
            data=date(2026, 9, 11),
            hora_inicio="18:30",
            hora_fim="20:00",
            numero_treino=3,
            origem="planeamento_global",
            e_jogo=False,
            ativa=True,
        )
        sessao_orfa_com_ficha = SessaoTreino(
            clube_id=clube.id,
            microciclo_id=micro.id,
            data=date(2026, 9, 10),
            numero_treino=2,
            origem="planeamento_global",
            e_jogo=False,
            ativa=True,
        )
        db.add_all([sessao_orfa, sessao_orfa_com_ficha])
        db.flush()
        plano_orfao = PlanoTreino(clube_id=clube.id, sessao_id=sessao_orfa_com_ficha.id)
        db.add(plano_orfao)
        db.flush()
        db.add(ExercicioPlano(clube_id=clube.id, plano_id=plano_orfao.id, ordem=1, nome="Exercício órfão"))
        db.flush()
        ids_orfas = {sessao_orfa.id, sessao_orfa_com_ficha.id}

        removidas, preservadas = _remover_sessoes_do_plano_semanal(
            db,
            semanal_id=999999,
            atribuicoes=[
                SimpleNamespace(
                    equipa_id=equipa.id,
                    data=date(2026, 9, 10),
                    hora_inicio=None,
                    hora_fim=None,
                ),
                SimpleNamespace(
                    equipa_id=equipa.id,
                    data=date(2026, 9, 11),
                    hora_inicio="18:30",
                    hora_fim="20:00",
                ),
            ],
        )
        assert (removidas, preservadas) == (2, 0)
        assert db.query(SessaoTreino).filter(SessaoTreino.id.in_(ids_orfas)).count() == 0

        sessao_orfa_arranque = SessaoTreino(
            clube_id=clube.id,
            microciclo_id=micro.id,
            data=date(2026, 9, 12),
            numero_treino=2,
            origem="planeamento_integrado",
            e_jogo=False,
            ativa=True,
        )
        sessao_manual = SessaoTreino(
            clube_id=clube.id,
            microciclo_id=micro.id,
            data=date(2026, 9, 13),
            numero_treino=3,
            origem="manual",
            e_jogo=False,
            ativa=True,
        )
        db.add_all([sessao_orfa_arranque, sessao_manual])
        db.flush()
        id_orfa_arranque = sessao_orfa_arranque.id
        id_manual = sessao_manual.id

        assert limpar_sessoes_geradas_orfas(db) == 1
        assert db.get(SessaoTreino, id_orfa_arranque) is None
        assert db.get(SessaoTreino, id_manual) is not None

        evento_atribuicao = EventoPlaneamentoClube(
            clube_id=clube.id,
            equipa_id=equipa.id,
            tipo=TipoEventoPlaneamentoClubeEnum.treino_equipa,
            titulo="Treino atribuído",
            data=date(2026, 9, 12),
            hora_inicio="20:00",
            hora_fim="21:30",
        )
        db.add(evento_atribuicao)
        db.flush()
        sessao_atribuicao = SessaoTreino(
            clube_id=clube.id,
            microciclo_id=micro.id,
            data=date(2026, 9, 12),
            hora_inicio="20:00",
            hora_fim="21:30",
            numero_treino=3,
            origem="manual",
            evento_planeamento_clube_id=evento_atribuicao.id,
            e_jogo=False,
            ativa=True,
        )
        db.add(sessao_atribuicao)
        db.flush()
        sessao_atribuicao_id = sessao_atribuicao.id

        assert _remover_sessoes_da_atribuicao(
            db,
            SimpleNamespace(
                equipa_id=equipa.id,
                data=date(2026, 9, 12),
                evento_id=evento_atribuicao.id,
                plano_semanal_id=999999,
                hora_inicio="20:00",
                hora_fim="21:30",
            ),
        ) == 1
        assert db.get(SessaoTreino, sessao_atribuicao_id) is None
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

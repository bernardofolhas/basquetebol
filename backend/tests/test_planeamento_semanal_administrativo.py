from datetime import date
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from clube_contexto import definir_clube_atual, repor_clube_atual
from database import Base
from models.atribuicao_espaco_semanal import (
    AtribuicaoEspacoSemanal,
    EstadoAtribuicaoEspacoEnum,
    TipoOcupacaoEspacoEnum,
)
from models.clube import Clube
from models.equipa import Equipa, EscalaoEnum, GeneroEnum
from models.espaco_treino import (
    DisponibilidadeEspacoTreino,
    EspacoTreino,
    IndisponibilidadeEspacoTreino,
    TipoEspacoTreinoEnum,
)
from models.indisponibilidade_treinador import IndisponibilidadeTreinador
from models.planeamento import Macrociclo, Mesociclo, Microciclo, SessaoTreino
from models.planeamento_clube import PlaneamentoClubeAnual, PlaneamentoClubeMensal, PlanoSemanalClube
from models.treinador import Treinador
from services.planeamento_semanal_administrativo_service import (
    gerar_grelha_slots,
    intervalos_operacionais,
    validar_local_sessao,
    validar_reserva,
)
from services.atribuicao_espaco_agenda_service import sincronizar_atribuicao_com_agenda
from services.atribuicao_espaco_visual_service import cor_espaco
from models.planeamento_clube import EventoPlaneamentoClube
from horarios import normalizar_hora


def _contexto():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessao = sessionmaker(bind=engine)()
    token = definir_clube_atual(1)
    clube = Clube(id=1, nome_oficial="Clube Teste", nome_curto="Teste", identificador="teste")
    equipa = Equipa(id=1, clube_id=1, nome="Sub-18", escalao=EscalaoEnum.sub18, genero=GeneroEnum.feminino)
    treinador = Treinador(id=1, clube_id=1, nome="Treinador Teste")
    espaco = EspacoTreino(id=1, clube_id=1, nome="Pavilhão", tipo=TipoEspacoTreinoEnum.pavilhao)
    anual = PlaneamentoClubeAnual(
        id=1, clube_id=1, epoca="2026/2027", titulo="Época", data_inicio=date(2026, 8, 1), data_fim=date(2027, 7, 31)
    )
    mensal = PlaneamentoClubeMensal(id=1, clube_id=1, planeamento_anual=anual, ano=2026, mes=8, titulo="Agosto")
    semanal = PlanoSemanalClube(
        id=1, clube_id=1, planeamento_mensal=mensal, titulo="Semana 1",
        data_inicio=date(2026, 8, 3), data_fim=date(2026, 8, 9),
    )
    sessao.add_all([clube, equipa, treinador, espaco, anual, mensal, semanal])
    sessao.commit()
    return sessao, token, espaco, equipa, treinador, semanal


def test_slots_sao_gerados_sem_criar_sessoes_tecnicas():
    db, token, espaco, _, _, semanal = _contexto()
    try:
        db.add(DisponibilidadeEspacoTreino(
            clube_id=1, espaco_id=espaco.id, dia_semana=0,
            hora_inicio="18:30", hora_fim="21:30", duracao_slot_minutos=90,
        ))
        db.commit()
        antes = db.query(SessaoTreino).count()
        grelha = gerar_grelha_slots(db, semanal)
        assert grelha["total"] == 2
        assert grelha["dias"][0]["slots"][0]["hora_inicio"] == "18:30"
        assert grelha["dias"][0]["slots"][-1]["hora_fim"] == "21:30"
        assert db.query(SessaoTreino).count() == antes
    finally:
        db.close()
        repor_clube_atual(token)


def test_mapa_mostra_reserva_mesmo_sem_slot_configurado():
    db, token, espaco, equipa, treinador, semanal = _contexto()
    try:
        db.add(DisponibilidadeEspacoTreino(
            clube_id=1, espaco_id=espaco.id, dia_semana=0,
            hora_inicio="18:00", hora_fim="19:30", duracao_slot_minutos=90,
        ))
        db.add(AtribuicaoEspacoSemanal(
            clube_id=1, plano_semanal_id=semanal.id, espaco_id=espaco.id,
            equipa_id=equipa.id, treinador_id=treinador.id, data=date(2026, 8, 3),
            hora_inicio="20:00", hora_fim="21:30", tipo_ocupacao=TipoOcupacaoEspacoEnum.treino_equipa,
            estado=EstadoAtribuicaoEspacoEnum.publicado,
        ))
        db.commit()

        grelha = gerar_grelha_slots(db, semanal)
        slots = grelha["dias"][0]["slots"]
        assert any(slot["atribuicao"] and slot["hora_inicio"] == "20:00" for slot in slots)
        assert grelha["espacos"] == [espaco]
    finally:
        db.close()
        repor_clube_atual(token)


def test_reserva_deteta_conflitos_de_espaco_equipa_e_treinador():
    db, token, espaco, equipa, treinador, semanal = _contexto()
    try:
        db.add(DisponibilidadeEspacoTreino(
            clube_id=1, espaco_id=espaco.id, dia_semana=0,
            hora_inicio="18:00", hora_fim="21:00", duracao_slot_minutos=90,
        ))
        db.add(AtribuicaoEspacoSemanal(
            clube_id=1, plano_semanal_id=semanal.id, espaco_id=espaco.id,
            equipa_id=equipa.id, treinador_id=treinador.id, data=date(2026, 8, 3),
            hora_inicio="18:00", hora_fim="19:30", tipo_ocupacao=TipoOcupacaoEspacoEnum.treino_equipa,
            estado=EstadoAtribuicaoEspacoEnum.publicado,
        ))
        db.commit()
        erros = validar_reserva(
            db, espaco_id=espaco.id, equipa_id=equipa.id, treinador_id=treinador.id,
            data_slot=date(2026, 8, 3), hora_inicio="18:30", hora_fim="19:00",
        )
        assert any("espaço já está ocupado" in erro for erro in erros)
        assert any("equipa já tem" in erro for erro in erros)
        assert any("treinador já está" in erro for erro in erros)
    finally:
        db.close()
        repor_clube_atual(token)


def test_horario_pontual_e_livre_dentro_do_periodo_operacional_e_aceite():
    db, token, espaco, equipa, treinador, _ = _contexto()
    try:
        assert validar_reserva(
            db,
            espaco_id=espaco.id,
            equipa_id=equipa.id,
            treinador_id=treinador.id,
            data_slot=date(2026, 8, 3),
            hora_inicio="18:00",
            hora_fim="19:30",
        ) == []
        erros = validar_reserva(
            db,
            espaco_id=espaco.id,
            equipa_id=equipa.id,
            treinador_id=treinador.id,
            data_slot=date(2026, 8, 3),
            hora_inicio="09:30",
            hora_fim="11:00",
        )
        assert erros == []
    finally:
        db.close()
        repor_clube_atual(token)


def test_bloqueio_e_validacao_informativa_do_local():
    db, token, espaco, equipa, treinador, semanal = _contexto()
    try:
        db.add(DisponibilidadeEspacoTreino(
            clube_id=1, espaco_id=espaco.id, dia_semana=0,
            hora_inicio="18:00", hora_fim="21:00", duracao_slot_minutos=90,
        ))
        db.add(IndisponibilidadeEspacoTreino(
            clube_id=1, espaco_id=espaco.id, data_inicio=date(2026, 8, 3),
            data_fim=date(2026, 8, 3), motivo="Manutenção",
        ))
        db.commit()
        erros = validar_reserva(
            db, espaco_id=espaco.id, equipa_id=equipa.id, treinador_id=treinador.id,
            data_slot=date(2026, 8, 3), hora_inicio="18:00", hora_fim="19:30",
        )
        assert any("Manutenção" in erro for erro in erros)

        db.query(IndisponibilidadeEspacoTreino).delete()
        db.add(AtribuicaoEspacoSemanal(
            clube_id=1, plano_semanal_id=semanal.id, espaco_id=espaco.id,
            equipa_id=equipa.id, treinador_id=treinador.id, data=date(2026, 8, 3),
            hora_inicio="18:00", hora_fim="19:30", tipo_ocupacao=TipoOcupacaoEspacoEnum.treino_equipa,
            estado=EstadoAtribuicaoEspacoEnum.publicado,
        ))
        db.commit()
        confirmada = validar_local_sessao(db, SimpleNamespace(
            data=date(2026, 8, 3), hora_inicio="18:00", hora_fim="19:30", local="Pavilhão"
        ), equipa.id)
        diferente = validar_local_sessao(db, SimpleNamespace(
            data=date(2026, 8, 3), hora_inicio="18:00", hora_fim="19:30", local="Outro local"
        ), equipa.id)
        sem_local = validar_local_sessao(db, SimpleNamespace(
            data=date(2026, 8, 3), hora_inicio="18:00", hora_fim="19:30", local=None
        ), equipa.id)
        sem_previsao = validar_local_sessao(db, SimpleNamespace(
            data=date(2026, 8, 4), hora_inicio="18:00", hora_fim="19:30", local="Pavilhão"
        ), equipa.id)
        assert confirmada["estado"] == "confirmado"
        assert diferente["estado"] == "diferente"
        assert sem_local["estado"] == "sem_local"
        assert sem_previsao["estado"] == "sem_previsao"
    finally:
        db.close()
        repor_clube_atual(token)


def test_indisponibilidade_do_treinador_impede_reserva_sem_alterar_plano():
    db, token, espaco, equipa, treinador, semanal = _contexto()
    try:
        db.add(DisponibilidadeEspacoTreino(
            clube_id=1, espaco_id=espaco.id, dia_semana=0,
            hora_inicio="18:00", hora_fim="21:00", duracao_slot_minutos=90,
        ))
        db.add(IndisponibilidadeTreinador(
            clube_id=1, treinador_id=treinador.id, data=date(2026, 8, 3),
            hora_inicio="18:00", hora_fim="19:30", motivo="Formação",
        ))
        db.commit()
        erros = validar_reserva(
            db, espaco_id=espaco.id, equipa_id=equipa.id, treinador_id=treinador.id,
            data_slot=date(2026, 8, 3), hora_inicio="18:00", hora_fim="19:30",
        )
        assert any("indicou indisponibilidade" in erro for erro in erros)
        assert db.query(AtribuicaoEspacoSemanal).count() == 0
        assert db.query(SessaoTreino).count() == 0
    finally:
        db.close()
        repor_clube_atual(token)


def test_reserva_publicada_cria_previsao_na_agenda_sem_criar_sessao_tecnica():
    db, token, espaco, equipa, treinador, semanal = _contexto()
    try:
        atribuicao = AtribuicaoEspacoSemanal(
            clube_id=1, plano_semanal_id=semanal.id, espaco_id=espaco.id,
            equipa_id=equipa.id, treinador_id=treinador.id, data=date(2026, 8, 3),
            hora_inicio="18:00", hora_fim="19:30", tipo_ocupacao=TipoOcupacaoEspacoEnum.treino_equipa,
            estado=EstadoAtribuicaoEspacoEnum.publicado,
        )
        db.add(atribuicao)
        db.flush()

        mensagem = sincronizar_atribuicao_com_agenda(db, atribuicao)
        db.commit()

        evento = db.query(EventoPlaneamentoClube).filter(EventoPlaneamentoClube.id == atribuicao.evento_id).one()
        assert evento.equipa_id == equipa.id
        assert evento.espaco_id == espaco.id
        assert evento.hora_inicio == "18:00"
        assert "agenda da equipa" in mensagem
        assert db.query(SessaoTreino).count() == 0
    finally:
        db.close()
        repor_clube_atual(token)


def test_reserva_do_clube_sobrepoe_horario_e_local_de_treino_do_treinador():
    """O clube define a logística, mesmo quando o treinador já preencheu a sessão."""
    db, token, espaco, equipa, treinador, semanal = _contexto()
    try:
        espaco.nome = "Vergílio"
        macro = Macrociclo(
            clube_id=1, equipa_id=equipa.id, numero=1,
            data_inicio=date(2026, 8, 3), data_fim=date(2026, 8, 9),
        )
        db.add(macro)
        db.flush()
        meso = Mesociclo(
            clube_id=1, macrociclo_id=macro.id, numero=1,
            data_inicio=date(2026, 8, 3), data_fim=date(2026, 8, 9),
        )
        db.add(meso)
        db.flush()
        micro = Microciclo(
            clube_id=1, mesociclo_id=meso.id, numero=1,
            data_inicio=date(2026, 8, 3), data_fim=date(2026, 8, 9),
        )
        db.add(micro)
        db.flush()
        sessao_completa = SessaoTreino(
            clube_id=1, microciclo_id=micro.id, data=date(2026, 8, 3),
            local="Doroteias", hora_inicio="18:30", hora_fim="20:00",
            volume_minutos=90, numero_treino=1, e_jogo=False, ativa=True,
        )
        sessao_sem_logistica = SessaoTreino(
            clube_id=1, microciclo_id=micro.id, data=date(2026, 8, 4),
            local=None, hora_inicio=None, hora_fim=None,
            volume_minutos=45, numero_treino=2, e_jogo=False, ativa=True,
        )
        db.add_all([sessao_completa, sessao_sem_logistica])
        db.flush()
        assert sessao_sem_logistica.volume_minutos is None

        atribuicao_completa = AtribuicaoEspacoSemanal(
            clube_id=1, plano_semanal_id=semanal.id, espaco_id=espaco.id,
            equipa_id=equipa.id, treinador_id=treinador.id, data=date(2026, 8, 3),
            hora_inicio="20:00", hora_fim="21:15",
            tipo_ocupacao=TipoOcupacaoEspacoEnum.treino_equipa,
            estado=EstadoAtribuicaoEspacoEnum.publicado,
        )
        atribuicao_sem_logistica = AtribuicaoEspacoSemanal(
            clube_id=1, plano_semanal_id=semanal.id, espaco_id=espaco.id,
            equipa_id=equipa.id, treinador_id=treinador.id, data=date(2026, 8, 4),
            hora_inicio="18:00", hora_fim="19:30",
            tipo_ocupacao=TipoOcupacaoEspacoEnum.treino_equipa,
            estado=EstadoAtribuicaoEspacoEnum.publicado,
        )
        db.add_all([atribuicao_completa, atribuicao_sem_logistica])
        db.flush()

        assert "atualizados" in sincronizar_atribuicao_com_agenda(db, atribuicao_completa)
        assert "atualizados" in sincronizar_atribuicao_com_agenda(db, atribuicao_sem_logistica)

        assert (sessao_completa.local, sessao_completa.hora_inicio, sessao_completa.hora_fim) == (
            "Vergílio", "20:00", "21:15"
        )
        assert (sessao_sem_logistica.local, sessao_sem_logistica.hora_inicio, sessao_sem_logistica.hora_fim) == (
            "Vergílio", "18:00", "19:30"
        )
        assert sessao_completa.volume_minutos == 75
        assert sessao_sem_logistica.volume_minutos == 90
    finally:
        db.close()
        repor_clube_atual(token)


def test_treino_fisico_publicado_cria_previsao_identificada_na_agenda():
    db, token, espaco, equipa, treinador, semanal = _contexto()
    try:
        atribuicao = AtribuicaoEspacoSemanal(
            clube_id=1, plano_semanal_id=semanal.id, espaco_id=espaco.id,
            equipa_id=equipa.id, treinador_id=treinador.id, data=date(2026, 8, 3),
            hora_inicio="18:00", hora_fim="19:30", tipo_ocupacao=TipoOcupacaoEspacoEnum.treino_fisico,
            estado=EstadoAtribuicaoEspacoEnum.publicado,
        )
        db.add(atribuicao)
        db.flush()

        mensagem = sincronizar_atribuicao_com_agenda(db, atribuicao)
        db.commit()

        evento = db.query(EventoPlaneamentoClube).filter(EventoPlaneamentoClube.id == atribuicao.evento_id).one()
        assert evento.titulo == "Treino físico"
        assert "agenda da equipa" in mensagem
    finally:
        db.close()
        repor_clube_atual(token)


def test_rascunho_nao_aparece_na_agenda_antes_do_envio():
    db, token, espaco, equipa, treinador, semanal = _contexto()
    try:
        atribuicao = AtribuicaoEspacoSemanal(
            clube_id=1, plano_semanal_id=semanal.id, espaco_id=espaco.id,
            equipa_id=equipa.id, treinador_id=treinador.id, data=date(2026, 8, 3),
            hora_inicio="18:00", hora_fim="19:30", tipo_ocupacao=TipoOcupacaoEspacoEnum.treino_equipa,
            estado=EstadoAtribuicaoEspacoEnum.rascunho,
        )
        db.add(atribuicao)
        db.flush()

        mensagem = sincronizar_atribuicao_com_agenda(db, atribuicao)

        assert "sem criar previsão" in mensagem
        assert db.query(EventoPlaneamentoClube).count() == 0
        assert db.query(SessaoTreino).count() == 0
    finally:
        db.close()
        repor_clube_atual(token)


def test_horas_escritas_com_h_sao_normalizadas_para_slots():
    assert normalizar_hora("18h30") == "18:30"
    assert normalizar_hora("20H00") == "20:00"


def test_grelha_operacional_tem_blocos_de_noventa_minutos_das_0930_as_2300():
    intervalos = intervalos_operacionais()

    assert intervalos[0] == ("09:30", "11:00")
    assert intervalos[-1] == ("21:30", "23:00")
    assert len(intervalos) == 9


def test_cada_espaco_recebe_uma_cor_estavel_no_mapa():
    assert cor_espaco(1) == cor_espaco(1)
    assert cor_espaco(1) != cor_espaco(2)

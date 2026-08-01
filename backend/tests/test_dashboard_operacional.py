from datetime import date, timedelta
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from main import app
from testsupport import TestClient


UTILIZADORES_TESTE = {
    "admin": {"username": "admin", "password": "admin123"},
}

NOME_EQUIPA_TESTE = "Equipa Dashboard Operacional Sprint 12"
NOME_TREINADOR_TESTE = "Treinador Dashboard Operacional Sprint 12"
NOME_ESPACO_TESTE = "Pavilhao Dashboard Operacional Sprint 12"
ADVERSARIO_JOGO_TESTE = "Adversario Dashboard Operacional Sprint 12"
TITULO_ANUAL_TESTE = "Anual Dashboard Operacional Sprint 12"
TITULO_MENSAL_TESTE = "Mensal Dashboard Operacional Sprint 12"
TITULO_SEMANAL_TESTE = "Semanal Dashboard Operacional Sprint 12"
TITULO_EVENTO_TESTE = "Treino Dashboard Operacional Sprint 12"


def _criar_client():
    return TestClient(app)


def _fazer_login(client: TestClient, perfil: str):
    response = client.post(
        "/login-form",
        data=UTILIZADORES_TESTE[perfil],
        follow_redirects=False,
    )
    assert response.status_code in [302, 303]
    assert response.headers["location"] == "/dashboard"


def _limpar_contexto_teste():
    from database import SessionLocal
    from models.atribuicao_espaco_semanal import AtribuicaoEspacoSemanal
    from models.equipa import Equipa
    from models.espaco_treino import EspacoTreino
    from models.jogo import Jogo
    from models.planeamento import Macrociclo, Mesociclo, Microciclo, SessaoTreino
    from models.planeamento_clube import EventoPlaneamentoClube, PlaneamentoClubeAnual, PlaneamentoClubeMensal, PlanoSemanalClube
    from models.treinador import Treinador

    db = SessionLocal()
    try:
        for atribuicao in db.query(AtribuicaoEspacoSemanal).all():
            if (
                atribuicao.plano_semanal and atribuicao.plano_semanal.titulo == TITULO_SEMANAL_TESTE
            ) or (
                atribuicao.espaco and atribuicao.espaco.nome == NOME_ESPACO_TESTE
            ):
                db.delete(atribuicao)

        for sessao in db.query(SessaoTreino).all():
            if (
                sessao.plano_semanal_clube and sessao.plano_semanal_clube.titulo == TITULO_SEMANAL_TESTE
            ) or (
                sessao.microciclo
                and sessao.microciclo.mesociclo
                and sessao.microciclo.mesociclo.macrociclo
                and sessao.microciclo.mesociclo.macrociclo.equipa
                and sessao.microciclo.mesociclo.macrociclo.equipa.nome == NOME_EQUIPA_TESTE
            ):
                db.delete(sessao)

        for evento in db.query(EventoPlaneamentoClube).filter(
            EventoPlaneamentoClube.titulo == TITULO_EVENTO_TESTE
        ).all():
            db.delete(evento)

        for jogo in db.query(Jogo).filter(Jogo.adversario == ADVERSARIO_JOGO_TESTE).all():
            db.delete(jogo)

        for semanal in db.query(PlanoSemanalClube).filter(PlanoSemanalClube.titulo == TITULO_SEMANAL_TESTE).all():
            db.delete(semanal)

        for mensal in db.query(PlaneamentoClubeMensal).filter(PlaneamentoClubeMensal.titulo == TITULO_MENSAL_TESTE).all():
            db.delete(mensal)

        for anual in db.query(PlaneamentoClubeAnual).filter(PlaneamentoClubeAnual.titulo == TITULO_ANUAL_TESTE).all():
            db.delete(anual)

        for micro in db.query(Microciclo).all():
            if micro.mesociclo and micro.mesociclo.macrociclo and micro.mesociclo.macrociclo.equipa and micro.mesociclo.macrociclo.equipa.nome == NOME_EQUIPA_TESTE:
                db.delete(micro)

        for meso in db.query(Mesociclo).all():
            if meso.macrociclo and meso.macrociclo.equipa and meso.macrociclo.equipa.nome == NOME_EQUIPA_TESTE:
                db.delete(meso)

        for macro in db.query(Macrociclo).all():
            if macro.equipa and macro.equipa.nome == NOME_EQUIPA_TESTE:
                db.delete(macro)

        db.commit()

        for treinador in db.query(Treinador).filter(Treinador.nome == NOME_TREINADOR_TESTE).all():
            db.delete(treinador)

        for espaco in db.query(EspacoTreino).filter(EspacoTreino.nome == NOME_ESPACO_TESTE).all():
            db.delete(espaco)

        for equipa in db.query(Equipa).filter(Equipa.nome == NOME_EQUIPA_TESTE).all():
            db.delete(equipa)

        db.commit()
    finally:
        db.close()


def _criar_contexto_operacional():
    from database import SessionLocal
    from models.atribuicao_espaco_semanal import (
        AtribuicaoEspacoSemanal,
        EstadoAtribuicaoEspacoEnum,
        OrigemAtribuicaoEspacoEnum,
        TipoOcupacaoEspacoEnum,
    )
    from models.equipa import Equipa, EscalaoEnum, GeneroEnum
    from models.espaco_treino import EspacoTreino, TipoEspacoTreinoEnum
    from models.jogo import Jogo
    from models.planeamento import Macrociclo, Mesociclo, Microciclo, SessaoTreino
    from models.planeamento_clube import (
        EventoPlaneamentoClube,
        OrigemEventoPlaneamentoClubeEnum,
        PlaneamentoClubeAnual,
        PlaneamentoClubeMensal,
        PlanoSemanalClube,
        TipoEventoPlaneamentoClubeEnum,
    )
    from models.treinador import Treinador

    hoje = date.today()
    fim_semana = hoje + timedelta(days=6)

    db = SessionLocal()
    try:
        equipa = Equipa(
            nome=NOME_EQUIPA_TESTE,
            escalao=EscalaoEnum.sub16,
            genero=GeneroEnum.masculino,
            seccionista=None,
        )
        db.add(equipa)
        db.commit()
        db.refresh(equipa)

        treinador = Treinador(nome=NOME_TREINADOR_TESTE)
        treinador.equipas.append(equipa)
        db.add(treinador)
        db.commit()
        db.refresh(treinador)

        macro = Macrociclo(
            numero=1,
            data_inicio=hoje,
            data_fim=fim_semana,
            equipa_id=equipa.id,
        )
        db.add(macro)
        db.commit()
        db.refresh(macro)

        meso = Mesociclo(
            numero=1,
            data_inicio=hoje,
            data_fim=fim_semana,
            macrociclo_id=macro.id,
        )
        db.add(meso)
        db.commit()
        db.refresh(meso)

        micro = Microciclo(
            numero=1,
            data_inicio=hoje,
            data_fim=fim_semana,
            tipo="operacional",
            mesociclo_id=meso.id,
        )
        db.add(micro)
        db.commit()
        db.refresh(micro)

        anual = PlaneamentoClubeAnual(
            epoca=f"{hoje.year}/{hoje.year + 1}",
            titulo=TITULO_ANUAL_TESTE,
            data_inicio=date(hoje.year, 1, 1),
            data_fim=date(hoje.year, 12, 31),
            ativo=True,
        )
        db.add(anual)
        db.commit()
        db.refresh(anual)

        mensal = PlaneamentoClubeMensal(
            planeamento_anual_id=anual.id,
            ano=hoje.year,
            mes=hoje.month,
            titulo=TITULO_MENSAL_TESTE,
            estado="ativo",
        )
        db.add(mensal)
        db.commit()
        db.refresh(mensal)

        semanal = PlanoSemanalClube(
            planeamento_mensal_id=mensal.id,
            titulo=TITULO_SEMANAL_TESTE,
            data_inicio=hoje,
            data_fim=fim_semana,
            estado="ativo",
            ultima_sincronizacao_resumo="Sincronização operacional de teste.",
        )
        db.add(semanal)
        db.commit()
        db.refresh(semanal)

        espaco = EspacoTreino(
            nome=NOME_ESPACO_TESTE,
            tipo=TipoEspacoTreinoEnum.pavilhao,
            localizacao="Pavilhão Central",
            ativo=True,
        )
        db.add(espaco)
        db.commit()
        db.refresh(espaco)

        jogo = Jogo(
            data=hoje,
            hora="16:00",
            local=NOME_ESPACO_TESTE,
            adversario=ADVERSARIO_JOGO_TESTE,
            competicao="Campeonato Distrital",
            em_casa=True,
            equipa_id=equipa.id,
        )
        db.add(jogo)
        db.commit()
        db.refresh(jogo)

        evento = EventoPlaneamentoClube(
            tipo=TipoEventoPlaneamentoClubeEnum.treino_equipa,
            titulo=TITULO_EVENTO_TESTE,
            data=hoje,
            hora_inicio="18:00",
            hora_fim="20:00",
            planeamento_mensal_id=mensal.id,
            plano_semanal_id=semanal.id,
            equipa_id=equipa.id,
            espaco_id=espaco.id,
            aplica_a_todas_equipas=False,
            origem=OrigemEventoPlaneamentoClubeEnum.manual,
        )
        evento.equipas = [equipa]
        db.add(evento)
        db.commit()
        db.refresh(evento)

        atribuicao = AtribuicaoEspacoSemanal(
            plano_semanal_id=semanal.id,
            espaco_id=espaco.id,
            equipa_id=equipa.id,
            evento_id=evento.id,
            data=hoje,
            hora_inicio="18:00",
            hora_fim="20:00",
            tipo_ocupacao=TipoOcupacaoEspacoEnum.treino_equipa,
            estado=EstadoAtribuicaoEspacoEnum.publicado,
            origem=OrigemAtribuicaoEspacoEnum.manual,
        )
        db.add(atribuicao)
        db.commit()

        sessao_sincronizada = SessaoTreino(
            data=hoje,
            local=NOME_ESPACO_TESTE,
            microciclo_id=micro.id,
            plano_semanal_clube_id=semanal.id,
            evento_planeamento_clube_id=evento.id,
            origem="planeamento_global",
            sincronizada=True,
            alterada_manual=False,
            ativa=True,
        )
        sessao_desatualizada = SessaoTreino(
            data=hoje + timedelta(days=1),
            local=NOME_ESPACO_TESTE,
            microciclo_id=micro.id,
            plano_semanal_clube_id=semanal.id,
            evento_planeamento_clube_id=evento.id,
            origem="planeamento_global",
            sincronizada=False,
            alterada_manual=False,
            ativa=True,
        )
        sessao_desativada = SessaoTreino(
            data=hoje + timedelta(days=2),
            local=NOME_ESPACO_TESTE,
            microciclo_id=micro.id,
            plano_semanal_clube_id=semanal.id,
            evento_planeamento_clube_id=evento.id,
            origem="planeamento_global",
            sincronizada=False,
            alterada_manual=False,
            ativa=False,
        )
        db.add_all([sessao_sincronizada, sessao_desatualizada, sessao_desativada])
        db.commit()

        return {
            "mensal_id": mensal.id,
            "semanal_id": semanal.id,
        }
    finally:
        db.close()


def test_dashboards_operacionais_e_detalhes_respondem_com_contexto():
    client = _criar_client()
    _limpar_contexto_teste()

    try:
        contexto = _criar_contexto_operacional()
        _fazer_login(client, "admin")

        response_dashboard = client.get("/dashboard/clube")
        assert response_dashboard.status_code == 200
        assert "Dashboard do Clube" in response_dashboard.text
        assert "Alertas Operacionais" in response_dashboard.text

        response_espacos = client.get("/dashboard/clube/espacos")
        assert response_espacos.status_code == 200
        assert "Dashboard de Ocupação de Espaços" in response_espacos.text
        assert NOME_ESPACO_TESTE in response_espacos.text

        response_carga = client.get("/dashboard/clube/carga")
        assert response_carga.status_code == 200
        assert "Dashboard de Carga de Treino" in response_carga.text
        assert NOME_EQUIPA_TESTE in response_carga.text

        response_executado = client.get("/dashboard/clube/executado")
        assert response_executado.status_code == 200
        assert "Planeado vs Estado Operacional" in response_executado.text
        assert NOME_EQUIPA_TESTE in response_executado.text

        response_sincronizacao = client.get("/dashboard/clube/sincronizacao")
        assert response_sincronizacao.status_code == 200
        assert "Dashboard de Sincronização" in response_sincronizacao.text
        assert NOME_EQUIPA_TESTE in response_sincronizacao.text

        response_mensal = client.get(f"/planeamento-clube/mensal/{contexto['mensal_id']}")
        assert response_mensal.status_code == 200
        assert "Resumo Operacional por Equipa" in response_mensal.text
        assert NOME_EQUIPA_TESTE in response_mensal.text
        assert ADVERSARIO_JOGO_TESTE in response_mensal.text

        response_semanal = client.get(f"/planeamento-clube/semanal/{contexto['semanal_id']}")
        assert response_semanal.status_code == 200
        assert "Mapa de Espaços" in response_semanal.text
        assert NOME_ESPACO_TESTE in response_semanal.text
        assert NOME_EQUIPA_TESTE in response_semanal.text
    finally:
        _limpar_contexto_teste()


def test_rotas_diretas_de_planeamento_mostram_registos_operacionais():
    client = _criar_client()
    _limpar_contexto_teste()

    try:
        _criar_contexto_operacional()
        _fazer_login(client, "admin")

        response_mensal = client.get("/planeamento-clube/mensal")
        assert response_mensal.status_code == 200
        assert TITULO_MENSAL_TESTE in response_mensal.text

        response_semanal = client.get("/planeamento-clube/semanal")
        assert response_semanal.status_code == 200
        assert TITULO_SEMANAL_TESTE in response_semanal.text
    finally:
        _limpar_contexto_teste()

from datetime import date, timedelta

from main import app
from testsupport import TestClient


UTILIZADORES_TESTE = {
    "admin": {"username": "admin", "password": "admin123"},
    "coordenador": {"username": "coord", "password": "coord123"},
    "treinador": {"username": "coach1", "password": "coach123"},
}

TITULO_ANUAL_TESTE = "Planeamento Clube Sprint 12"
TITULO_ANUAL_EDITADO = "Planeamento Clube Sprint 12 Editado"
TITULO_MENSAL_TESTE = "Mensal Sprint 12"
TITULO_MENSAL_EDITADO = "Mensal Sprint 12 Editado"
TITULO_SEMANAL_TESTE = "Semanal Sprint 12"
TITULO_SEMANAL_EDITADO = "Semanal Sprint 12 Editado"
TITULO_EVENTO_MANUAL = "Evento Manual Sprint 12"
TITULO_EVENTO_EDITADO = "Evento Manual Sprint 12 Editado"
TITULO_ATIVIDADE_TESTE = "Atividade Sprint 12"
NOME_EQUIPA_TESTE = "Equipa Planeamento Sprint 12"
NOME_EQUIPA_TESTE_2 = "Equipa Planeamento Sprint 12 B"
NOME_EQUIPA_SINCRONIZACAO_1 = "Equipa Sincronizacao Sprint 12 A"
NOME_EQUIPA_SINCRONIZACAO_2 = "Equipa Sincronizacao Sprint 12 B"
ADVERSARIO_JOGO_TESTE = "Adversario Sprint 12"
NOME_ESPACO_TESTE = "Pavilhao Sprint 12"
NOME_ESPACO_EDITADO = "Pavilhao Sprint 12 Editado"
NOME_ESPACO_ELIMINAR = "Ginasio Sprint 12 Eliminar"
TITULO_ANUAL_SINCRONIZACAO = "Planeamento Sincronizacao Sprint 12"
TITULO_MENSAL_SINCRONIZACAO = "Mensal Sincronizacao Sprint 12"
TITULO_SEMANAL_SINCRONIZACAO = "Semanal Sincronizacao Sprint 12"
TITULO_EVENTO_SINCRONIZACAO_UNICO = "Evento Sincronizacao Equipa Unica"
TITULO_EVENTO_SINCRONIZACAO_MULTIPLO = "Evento Sincronizacao Multi Equipa"
TITULO_EVENTO_SINCRONIZACAO_GLOBAL = "Evento Sincronizacao Todas Equipas"


def _criar_client():
    """Cria um cliente de teste isolado para cada cenário."""
    return TestClient(app)


def _fazer_login(client: TestClient, perfil: str):
    """Autentica um utilizador de teste e mantém a sessão."""
    response = client.post(
        "/login-form",
        data=UTILIZADORES_TESTE[perfil],
        follow_redirects=False,
    )

    assert response.status_code in [302, 303]
    assert response.headers["location"] == "/dashboard"


def _limpar_planeamento_teste():
    from database import SessionLocal
    from models.atividade import Atividade
    from models.atribuicao_espaco_semanal import AtribuicaoEspacoSemanal
    from models.equipa import Equipa
    from models.espaco_treino import EspacoTreino
    from models.jogo import Jogo
    from models.planeamento import Macrociclo, Mesociclo, Microciclo, SessaoTreino
    from models.planeamento_clube import EventoPlaneamentoClube, PlaneamentoClubeAnual

    db = SessionLocal()
    try:
        atividades = db.query(Atividade).filter(Atividade.titulo == TITULO_ATIVIDADE_TESTE).all()
        jogos = db.query(Jogo).filter(Jogo.adversario == ADVERSARIO_JOGO_TESTE).all()

        for registo in db.query(EventoPlaneamentoClube).filter(
            EventoPlaneamentoClube.titulo.in_([
                TITULO_EVENTO_MANUAL,
                TITULO_EVENTO_EDITADO,
                TITULO_EVENTO_SINCRONIZACAO_UNICO,
                TITULO_EVENTO_SINCRONIZACAO_MULTIPLO,
                TITULO_EVENTO_SINCRONIZACAO_GLOBAL,
            ])
        ).all():
            db.delete(registo)

        for sessao in db.query(SessaoTreino).filter(
            SessaoTreino.plano_semanal_clube_id != None
        ).all():
            if (
                sessao.plano_semanal_clube
                and sessao.plano_semanal_clube.titulo == TITULO_SEMANAL_SINCRONIZACAO
            ):
                db.delete(sessao)

        for atribuicao in db.query(AtribuicaoEspacoSemanal).all():
            if (
                atribuicao.espaco and atribuicao.espaco.nome in [NOME_ESPACO_TESTE, NOME_ESPACO_EDITADO, NOME_ESPACO_ELIMINAR]
            ) or (
                atribuicao.plano_semanal and atribuicao.plano_semanal.titulo == TITULO_SEMANAL_TESTE
            ):
                db.delete(atribuicao)

        for jogo in jogos:
            for evento in db.query(EventoPlaneamentoClube).filter(EventoPlaneamentoClube.jogo_id == jogo.id).all():
                db.delete(evento)

        for atividade in atividades:
            for evento in db.query(EventoPlaneamentoClube).filter(EventoPlaneamentoClube.atividade_id == atividade.id).all():
                db.delete(evento)

        for registo in db.query(PlaneamentoClubeAnual).filter(
            PlaneamentoClubeAnual.titulo.in_([
                TITULO_ANUAL_TESTE,
                TITULO_ANUAL_EDITADO,
                TITULO_ANUAL_SINCRONIZACAO,
            ])
        ).all():
            db.delete(registo)

        for atividade in atividades:
            db.delete(atividade)

        for jogo in jogos:
            db.delete(jogo)

        for microciclo in db.query(Microciclo).all():
            if microciclo.mesociclo and microciclo.mesociclo.macrociclo and microciclo.mesociclo.macrociclo.equipa and microciclo.mesociclo.macrociclo.equipa.nome in [NOME_EQUIPA_SINCRONIZACAO_1, NOME_EQUIPA_SINCRONIZACAO_2]:
                db.delete(microciclo)

        for mesociclo in db.query(Mesociclo).all():
            if mesociclo.macrociclo and mesociclo.macrociclo.equipa and mesociclo.macrociclo.equipa.nome in [NOME_EQUIPA_SINCRONIZACAO_1, NOME_EQUIPA_SINCRONIZACAO_2]:
                db.delete(mesociclo)

        for macrociclo in db.query(Macrociclo).all():
            if macrociclo.equipa and macrociclo.equipa.nome in [NOME_EQUIPA_SINCRONIZACAO_1, NOME_EQUIPA_SINCRONIZACAO_2]:
                db.delete(macrociclo)

        for equipa in db.query(Equipa).filter(Equipa.nome.in_([
            NOME_EQUIPA_TESTE,
            NOME_EQUIPA_TESTE_2,
            NOME_EQUIPA_SINCRONIZACAO_1,
            NOME_EQUIPA_SINCRONIZACAO_2,
        ])).all():
            db.delete(equipa)

        for espaco in db.query(EspacoTreino).filter(
            EspacoTreino.nome.in_([NOME_ESPACO_TESTE, NOME_ESPACO_EDITADO, NOME_ESPACO_ELIMINAR])
        ).all():
            db.delete(espaco)

        db.commit()
    finally:
        db.close()


def _criar_suporte_eventos():
    from database import SessionLocal
    from models.atividade import Atividade
    from models.equipa import Equipa, EscalaoEnum, GeneroEnum
    from models.jogo import Jogo

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

        jogo = Jogo(
            data=date.fromisoformat("2025-09-10"),
            hora="18:00",
            local="Pavilhao Municipal",
            adversario=ADVERSARIO_JOGO_TESTE,
            competicao="Torneio de Preparacao",
            em_casa=True,
            observacoes="Jogo de teste",
            equipa_id=equipa.id,
        )
        atividade = Atividade(
            titulo=TITULO_ATIVIDADE_TESTE,
            data=date.fromisoformat("2025-09-12"),
            local="Sede do Clube",
            tipo="Social",
            descricao="Atividade de integracao",
            observacoes="Atividade de teste",
        )
        db.add(jogo)
        db.add(atividade)
        db.commit()
        db.refresh(jogo)
        db.refresh(atividade)
        return equipa.id, jogo.id, atividade.id
    finally:
        db.close()


def _criar_equipas_teste():
    from database import SessionLocal
    from models.equipa import Equipa, EscalaoEnum, GeneroEnum

    db = SessionLocal()
    try:
        equipa_1 = Equipa(
            nome=NOME_EQUIPA_TESTE,
            escalao=EscalaoEnum.sub16,
            genero=GeneroEnum.masculino,
            seccionista=None,
        )
        equipa_2 = Equipa(
            nome=NOME_EQUIPA_TESTE_2,
            escalao=EscalaoEnum.sub18,
            genero=GeneroEnum.feminino,
            seccionista=None,
        )
        db.add(equipa_1)
        db.add(equipa_2)
        db.commit()
        db.refresh(equipa_1)
        db.refresh(equipa_2)
        return equipa_1.id, equipa_2.id
    finally:
        db.close()


def _obter_ids_planeamento_teste():
    from database import SessionLocal
    from models.planeamento_clube import EventoPlaneamentoClube, PlaneamentoClubeAnual, PlaneamentoClubeMensal, PlanoSemanalClube

    db = SessionLocal()
    try:
        anual = db.query(PlaneamentoClubeAnual).filter(PlaneamentoClubeAnual.titulo == TITULO_ANUAL_TESTE).first()
        mensal = db.query(PlaneamentoClubeMensal).filter(PlaneamentoClubeMensal.titulo == TITULO_MENSAL_TESTE).first()
        semanal = db.query(PlanoSemanalClube).filter(PlanoSemanalClube.titulo == TITULO_SEMANAL_TESTE).first()
        evento_manual = db.query(EventoPlaneamentoClube).filter(
            EventoPlaneamentoClube.titulo.in_([TITULO_EVENTO_MANUAL, TITULO_EVENTO_EDITADO])
        ).first()
        return (
            anual.id if anual else None,
            mensal.id if mensal else None,
            semanal.id if semanal else None,
            evento_manual.id if evento_manual else None,
        )
    finally:
        db.close()


def _obter_espaco_por_nome(nome: str):
    from database import SessionLocal
    from models.espaco_treino import EspacoTreino

    db = SessionLocal()
    try:
        espaco = db.query(EspacoTreino).filter(EspacoTreino.nome == nome).first()
        return espaco.id if espaco else None
    finally:
        db.close()


def _obter_atribuicao_por_espaco(espaco_id: int):
    from database import SessionLocal
    from models.atribuicao_espaco_semanal import AtribuicaoEspacoSemanal

    db = SessionLocal()
    try:
        atribuicao = db.query(AtribuicaoEspacoSemanal).filter(AtribuicaoEspacoSemanal.espaco_id == espaco_id).first()
        return atribuicao.id if atribuicao else None
    finally:
        db.close()


def _obter_ids_por_titulos():
    from database import SessionLocal
    from models.planeamento_clube import PlaneamentoClubeAnual, PlaneamentoClubeMensal, PlanoSemanalClube

    db = SessionLocal()
    try:
        anual = db.query(PlaneamentoClubeAnual).filter(
            PlaneamentoClubeAnual.titulo.in_([TITULO_ANUAL_TESTE, TITULO_ANUAL_EDITADO])
        ).first()
        mensal = db.query(PlaneamentoClubeMensal).filter(
            PlaneamentoClubeMensal.titulo.in_([TITULO_MENSAL_TESTE, TITULO_MENSAL_EDITADO])
        ).first()
        semanal = db.query(PlanoSemanalClube).filter(
            PlanoSemanalClube.titulo.in_([TITULO_SEMANAL_TESTE, TITULO_SEMANAL_EDITADO])
        ).first()
        return anual.id if anual else None, mensal.id if mensal else None, semanal.id if semanal else None
    finally:
        db.close()


def _criar_estrutura_semanal_teste(client: TestClient):
    client.post(
        "/planeamento-clube/anual/novo",
        data={
            "epoca": "2025/2026",
            "titulo": TITULO_ANUAL_TESTE,
            "data_inicio": "2025-09-01",
            "data_fim": "2026-06-30",
            "objetivos_gerais": "Objetivos gerais do clube",
            "observacoes": "Observacoes de teste",
            "ativo": "true",
        },
        follow_redirects=False,
    )
    anual_id, _, _, _ = _obter_ids_planeamento_teste()

    client.post(
        f"/planeamento-clube/anual/{anual_id}/mensal/novo",
        data={
            "ano": "2025",
            "mes": "9",
            "titulo": TITULO_MENSAL_TESTE,
            "objetivos_mes": "Objetivos mensais",
            "observacoes": "Observacoes mensais",
            "estado": "ativo",
        },
        follow_redirects=False,
    )
    _, mensal_id, _, _ = _obter_ids_planeamento_teste()

    client.post(
        f"/planeamento-clube/mensal/{mensal_id}/semanal/novo",
        data={
            "titulo": TITULO_SEMANAL_TESTE,
            "data_inicio": "2025-09-01",
            "data_fim": "2025-09-07",
            "observacoes": "Observacoes semanais",
            "estado": "ativo",
        },
        follow_redirects=False,
    )
    _, _, semanal_id, _ = _obter_ids_planeamento_teste()
    return anual_id, mensal_id, semanal_id


def _criar_contexto_sincronizacao(criar_microciclos: bool = True):
    from database import SessionLocal
    from models.equipa import Equipa, EscalaoEnum, GeneroEnum
    from models.planeamento import Macrociclo, Mesociclo, Microciclo
    from models.planeamento_clube import (
        EventoPlaneamentoClube,
        OrigemEventoPlaneamentoClubeEnum,
        PlaneamentoClubeAnual,
        PlaneamentoClubeMensal,
        PlanoSemanalClube,
        TipoEventoPlaneamentoClubeEnum,
    )

    db = SessionLocal()
    try:
        equipa_1 = Equipa(
            nome=NOME_EQUIPA_SINCRONIZACAO_1,
            escalao=EscalaoEnum.sub16,
            genero=GeneroEnum.masculino,
            seccionista=None,
        )
        equipa_2 = Equipa(
            nome=NOME_EQUIPA_SINCRONIZACAO_2,
            escalao=EscalaoEnum.sub18,
            genero=GeneroEnum.feminino,
            seccionista=None,
        )
        db.add_all([equipa_1, equipa_2])
        db.commit()
        db.refresh(equipa_1)
        db.refresh(equipa_2)

        anual = PlaneamentoClubeAnual(
            epoca="2025/2026",
            titulo=TITULO_ANUAL_SINCRONIZACAO,
            data_inicio=date.fromisoformat("2025-09-01"),
            data_fim=date.fromisoformat("2026-06-30"),
            objetivos_gerais="Sincronização semanal",
            observacoes=None,
            ativo=True,
        )
        db.add(anual)
        db.commit()
        db.refresh(anual)

        mensal = PlaneamentoClubeMensal(
            planeamento_anual_id=anual.id,
            ano=2025,
            mes=9,
            titulo=TITULO_MENSAL_SINCRONIZACAO,
            objetivos_mes="Sincronização mensal",
            observacoes=None,
            estado="rascunho",
        )
        db.add(mensal)
        db.commit()
        db.refresh(mensal)

        semanal = PlanoSemanalClube(
            planeamento_mensal_id=mensal.id,
            titulo=TITULO_SEMANAL_SINCRONIZACAO,
            data_inicio=date.fromisoformat("2025-09-08"),
            data_fim=date.fromisoformat("2025-09-14"),
            observacoes="Semana de sincronização",
            estado="rascunho",
        )
        db.add(semanal)
        db.commit()
        db.refresh(semanal)

        for indice, equipa in enumerate([equipa_1, equipa_2], start=1):
            macrociclo = Macrociclo(
                numero=1,
                data_inicio=date.fromisoformat("2025-09-01"),
                data_fim=date.fromisoformat("2025-09-30"),
                equipa_id=equipa.id,
            )
            db.add(macrociclo)
            db.commit()
            db.refresh(macrociclo)

            mesociclo = Mesociclo(
                numero=1,
                data_inicio=date.fromisoformat("2025-09-01"),
                data_fim=date.fromisoformat("2025-09-30"),
                macrociclo_id=macrociclo.id,
            )
            db.add(mesociclo)
            db.commit()
            db.refresh(mesociclo)

            if criar_microciclos:
                microciclo = Microciclo(
                    numero=indice,
                    data_inicio=date.fromisoformat("2025-09-08"),
                    data_fim=date.fromisoformat("2025-09-14"),
                    tipo="competitivo",
                    mesociclo_id=mesociclo.id,
                )
                db.add(microciclo)
                db.commit()

        evento_unico = EventoPlaneamentoClube(
            tipo=TipoEventoPlaneamentoClubeEnum.treino_equipa,
            titulo=TITULO_EVENTO_SINCRONIZACAO_UNICO,
            data=date.fromisoformat("2025-09-09"),
            hora_inicio="18:00",
            hora_fim="19:30",
            plano_semanal_id=semanal.id,
            equipa_id=equipa_1.id,
            aplica_a_todas_equipas=False,
            origem=OrigemEventoPlaneamentoClubeEnum.manual,
        )
        evento_multi = EventoPlaneamentoClube(
            tipo=TipoEventoPlaneamentoClubeEnum.treino_individual,
            titulo=TITULO_EVENTO_SINCRONIZACAO_MULTIPLO,
            data=date.fromisoformat("2025-09-10"),
            hora_inicio="17:00",
            hora_fim="18:00",
            plano_semanal_id=semanal.id,
            equipa_id=equipa_1.id,
            aplica_a_todas_equipas=False,
            origem=OrigemEventoPlaneamentoClubeEnum.manual,
        )
        evento_multi.equipas = [equipa_1, equipa_2]

        evento_global = EventoPlaneamentoClube(
            tipo=TipoEventoPlaneamentoClubeEnum.treino_equipa,
            titulo=TITULO_EVENTO_SINCRONIZACAO_GLOBAL,
            data=date.fromisoformat("2025-09-11"),
            hora_inicio="19:00",
            hora_fim="20:30",
            plano_semanal_id=semanal.id,
            equipa_id=None,
            aplica_a_todas_equipas=True,
            origem=OrigemEventoPlaneamentoClubeEnum.manual,
        )

        db.add_all([evento_unico, evento_multi, evento_global])
        db.commit()
        db.refresh(evento_unico)
        db.refresh(evento_multi)
        db.refresh(evento_global)

        return {
            "equipa_1_id": equipa_1.id,
            "equipa_2_id": equipa_2.id,
            "semanal_id": semanal.id,
            "evento_unico_id": evento_unico.id,
            "evento_multi_id": evento_multi.id,
            "evento_global_id": evento_global.id,
        }
    finally:
        db.close()


def _obter_sessoes_sincronizacao():
    from database import SessionLocal
    from models.planeamento import SessaoTreino

    db = SessionLocal()
    try:
        return db.query(SessaoTreino).filter(
            SessaoTreino.plano_semanal_clube_id != None
        ).all()
    finally:
        db.close()


def _obter_evento_por_jogo(jogo_id: int):
    from database import SessionLocal
    from models.planeamento_clube import EventoPlaneamentoClube

    db = SessionLocal()
    try:
        evento = db.query(EventoPlaneamentoClube).filter(EventoPlaneamentoClube.jogo_id == jogo_id).first()
        return evento.id if evento else None
    finally:
        db.close()


def _obter_evento_por_atividade(atividade_id: int):
    from database import SessionLocal
    from models.planeamento_clube import EventoPlaneamentoClube

    db = SessionLocal()
    try:
        evento = db.query(EventoPlaneamentoClube).filter(EventoPlaneamentoClube.atividade_id == atividade_id).first()
        return evento.id if evento else None
    finally:
        db.close()


def _obter_evento_manual():
    from database import SessionLocal
    from models.planeamento_clube import EventoPlaneamentoClube

    db = SessionLocal()
    try:
        evento = db.query(EventoPlaneamentoClube).filter(
            EventoPlaneamentoClube.titulo.in_([TITULO_EVENTO_MANUAL, TITULO_EVENTO_EDITADO])
        ).first()
        if evento:
            _ = [equipa.id for equipa in evento.equipas]
        return evento
    finally:
        db.close()


def test_coordenador_consegue_listar_eventos():
    client = _criar_client()
    _fazer_login(client, "coordenador")

    response = client.get("/planeamento-clube/eventos", follow_redirects=False)

    assert response.status_code == 200


def test_administrador_consegue_listar_eventos():
    client = _criar_client()
    _fazer_login(client, "admin")

    response = client.get("/planeamento-clube/eventos", follow_redirects=False)

    assert response.status_code == 200


def test_treinador_nao_consegue_aceder_planeamento_clube():
    client = _criar_client()
    _fazer_login(client, "treinador")

    response = client.get("/planeamento-clube/eventos", follow_redirects=False)

    assert response.status_code in [302, 307]
    assert response.headers["location"] == "/dashboard"


def test_coordenador_consegue_gerir_espacos():
    client = _criar_client()
    _fazer_login(client, "coordenador")

    response = client.get("/planeamento-clube/espacos", follow_redirects=False)

    assert response.status_code == 200


def test_administrador_consegue_gerir_espacos():
    client = _criar_client()
    _fazer_login(client, "admin")

    response = client.get("/planeamento-clube/espacos", follow_redirects=False)

    assert response.status_code == 200


def test_treinador_nao_consegue_gerir_espacos():
    client = _criar_client()
    _fazer_login(client, "treinador")

    response = client.get("/planeamento-clube/espacos", follow_redirects=False)

    assert response.status_code in [302, 307]
    assert response.headers["location"] == "/dashboard"


def test_criacao_de_espaco_funciona():
    client = _criar_client()
    _fazer_login(client, "coordenador")
    _limpar_planeamento_teste()

    try:
        response = client.post(
            "/planeamento-clube/espacos/novo",
            data={
                "nome": NOME_ESPACO_TESTE,
                "tipo": "pavilhao",
                "localizacao": "Complexo Desportivo",
                "capacidade": "120",
                "ativo": "true",
                "observacoes": "Espaco criado em teste",
            },
            follow_redirects=False,
        )

        assert response.status_code == 303
        espaco_id = _obter_espaco_por_nome(NOME_ESPACO_TESTE)
        assert espaco_id is not None

        detalhe = client.get(f"/planeamento-clube/espacos/{espaco_id}", follow_redirects=False)
        assert detalhe.status_code == 200
        assert NOME_ESPACO_TESTE in detalhe.text
    finally:
        _limpar_planeamento_teste()


def test_edicao_de_espaco_funciona():
    client = _criar_client()
    _fazer_login(client, "admin")
    _limpar_planeamento_teste()

    try:
        client.post(
            "/planeamento-clube/espacos/novo",
            data={
                "nome": NOME_ESPACO_TESTE,
                "tipo": "pavilhao",
                "localizacao": "Complexo Desportivo",
                "capacidade": "120",
                "ativo": "true",
                "observacoes": "Espaco criado em teste",
            },
            follow_redirects=False,
        )
        espaco_id = _obter_espaco_por_nome(NOME_ESPACO_TESTE)
        assert espaco_id is not None

        response = client.post(
            f"/planeamento-clube/espacos/{espaco_id}/editar",
            data={
                "nome": NOME_ESPACO_EDITADO,
                "tipo": "ginasio",
                "localizacao": "Piso superior",
                "capacidade": "80",
                "ativo": "false",
                "observacoes": "Espaco editado em teste",
            },
            follow_redirects=False,
        )

        assert response.status_code == 303
        detalhe = client.get(f"/planeamento-clube/espacos/{espaco_id}", follow_redirects=False)
        assert detalhe.status_code == 200
        assert NOME_ESPACO_EDITADO in detalhe.text
    finally:
        _limpar_planeamento_teste()


def test_eliminacao_de_espaco_funciona():
    client = _criar_client()
    _fazer_login(client, "coordenador")
    _limpar_planeamento_teste()

    try:
        client.post(
            "/planeamento-clube/espacos/novo",
            data={
                "nome": NOME_ESPACO_ELIMINAR,
                "tipo": "outro",
                "localizacao": "Sala multiusos",
                "capacidade": "25",
                "ativo": "true",
                "observacoes": "",
            },
            follow_redirects=False,
        )
        espaco_id = _obter_espaco_por_nome(NOME_ESPACO_ELIMINAR)
        assert espaco_id is not None

        response = client.post(f"/planeamento-clube/espacos/{espaco_id}/eliminar", follow_redirects=False)

        assert response.status_code == 303
        assert _obter_espaco_por_nome(NOME_ESPACO_ELIMINAR) is None
    finally:
        _limpar_planeamento_teste()


def test_fluxo_criacao_e_detalhe_planeamento_clube_com_eventos():
    client = _criar_client()
    _fazer_login(client, "coordenador")
    _limpar_planeamento_teste()

    try:
        response_anual = client.post(
            "/planeamento-clube/anual/novo",
            data={
                "epoca": "2025/2026",
                "titulo": TITULO_ANUAL_TESTE,
                "data_inicio": "2025-09-01",
                "data_fim": "2026-06-30",
                "objetivos_gerais": "Objetivos gerais do clube",
                "observacoes": "Observacoes de teste",
                "ativo": "true",
            },
            follow_redirects=False,
        )
        assert response_anual.status_code == 303

        anual_id, _, _, _ = _obter_ids_planeamento_teste()
        assert anual_id is not None

        response_mensal = client.post(
            f"/planeamento-clube/anual/{anual_id}/mensal/novo",
            data={
                "ano": "2025",
                "mes": "9",
                "titulo": TITULO_MENSAL_TESTE,
                "objetivos_mes": "Objetivos mensais",
                "observacoes": "Observacoes mensais",
                "estado": "ativo",
            },
            follow_redirects=False,
        )
        assert response_mensal.status_code == 303

        _, mensal_id, _, _ = _obter_ids_planeamento_teste()
        assert mensal_id is not None

        response_semanal = client.post(
            f"/planeamento-clube/mensal/{mensal_id}/semanal/novo",
            data={
                "titulo": TITULO_SEMANAL_TESTE,
                "data_inicio": "2025-09-01",
                "data_fim": "2025-09-07",
                "observacoes": "Observacoes semanais",
                "estado": "ativo",
            },
            follow_redirects=False,
        )
        assert response_semanal.status_code == 303

        _, _, semanal_id, _ = _obter_ids_planeamento_teste()
        assert semanal_id is not None

        response_evento = client.post(
            "/planeamento-clube/eventos/novo",
            data={
                "tipo": "evento_clube",
                "titulo": TITULO_EVENTO_MANUAL,
                "descricao": "Descricao do evento",
                "data_evento": "2025-09-05",
                "hora_inicio": "10:00",
                "hora_fim": "12:00",
                "planeamento_anual_id": str(anual_id),
                "planeamento_mensal_id": str(mensal_id),
                "plano_semanal_id": str(semanal_id),
                "equipa_id": "",
                "treinador_id": "",
                "observacoes": "Observacoes do evento",
            },
            follow_redirects=False,
        )
        assert response_evento.status_code == 303

        _, _, _, evento_id = _obter_ids_planeamento_teste()
        assert evento_id is not None

        detalhe_evento = client.get(f"/planeamento-clube/eventos/{evento_id}", follow_redirects=False)
        assert detalhe_evento.status_code == 200

        detalhe_anual = client.get(f"/planeamento-clube/anual/{anual_id}")
        detalhe_mensal = client.get(f"/planeamento-clube/mensal/{mensal_id}")
        detalhe_semanal = client.get(f"/planeamento-clube/semanal/{semanal_id}")

        assert TITULO_EVENTO_MANUAL in detalhe_anual.text
        assert TITULO_EVENTO_MANUAL in detalhe_mensal.text
        assert TITULO_EVENTO_MANUAL in detalhe_semanal.text
    finally:
        _limpar_planeamento_teste()


def test_criacao_de_evento_com_espaco_associado_funciona():
    client = _criar_client()
    _fazer_login(client, "coordenador")
    _limpar_planeamento_teste()

    try:
        client.post(
            "/planeamento-clube/espacos/novo",
            data={
                "nome": NOME_ESPACO_TESTE,
                "tipo": "pavilhao",
                "localizacao": "Complexo Desportivo",
                "capacidade": "120",
                "ativo": "true",
                "observacoes": "",
            },
            follow_redirects=False,
        )
        espaco_id = _obter_espaco_por_nome(NOME_ESPACO_TESTE)

        response = client.post(
            "/planeamento-clube/eventos/novo",
            data={
                "tipo": "evento_clube",
                "titulo": TITULO_EVENTO_MANUAL,
                "descricao": "Descricao do evento",
                "data_evento": "2025-09-05",
                "hora_inicio": "10:00",
                "hora_fim": "12:00",
                "planeamento_anual_id": "",
                "planeamento_mensal_id": "",
                "plano_semanal_id": "",
                "equipas_ids": [],
                "espaco_id": str(espaco_id),
                "treinador_id": "",
                "aplica_a_todas_equipas": "false",
                "observacoes": "Observacoes do evento",
            },
            follow_redirects=False,
        )

        assert response.status_code == 303
        evento = _obter_evento_manual()
        assert evento is not None
        assert evento.espaco_id == espaco_id
    finally:
        _limpar_planeamento_teste()


def test_criacao_de_evento_com_uma_equipa_funciona():
    client = _criar_client()
    _fazer_login(client, "coordenador")
    _limpar_planeamento_teste()

    try:
        equipa_id, _ = _criar_equipas_teste()

        response = client.post(
            "/planeamento-clube/eventos/novo",
            data={
                "tipo": "evento_clube",
                "titulo": TITULO_EVENTO_MANUAL,
                "descricao": "",
                "data_evento": "2025-09-05",
                "hora_inicio": "10:00",
                "hora_fim": "12:00",
                "planeamento_anual_id": "",
                "planeamento_mensal_id": "",
                "plano_semanal_id": "",
                "equipas_ids": [str(equipa_id)],
                "espaco_id": "",
                "treinador_id": "",
                "aplica_a_todas_equipas": "false",
                "observacoes": "",
            },
            follow_redirects=False,
        )

        assert response.status_code == 303
        evento = _obter_evento_manual()
        assert evento is not None
        assert [equipa.id for equipa in evento.equipas] == [equipa_id]
    finally:
        _limpar_planeamento_teste()


def test_criacao_de_evento_com_varias_equipas_funciona():
    client = _criar_client()
    _fazer_login(client, "admin")
    _limpar_planeamento_teste()

    try:
        equipa_id_1, equipa_id_2 = _criar_equipas_teste()

        response = client.post(
            "/planeamento-clube/eventos/novo",
            data={
                "tipo": "evento_clube",
                "titulo": TITULO_EVENTO_MANUAL,
                "descricao": "",
                "data_evento": "2025-09-05",
                "hora_inicio": "10:00",
                "hora_fim": "12:00",
                "planeamento_anual_id": "",
                "planeamento_mensal_id": "",
                "plano_semanal_id": "",
                "equipas_ids": [str(equipa_id_1), str(equipa_id_2)],
                "espaco_id": "",
                "treinador_id": "",
                "aplica_a_todas_equipas": "false",
                "observacoes": "",
            },
            follow_redirects=False,
        )

        assert response.status_code == 303
        evento = _obter_evento_manual()
        assert evento is not None
        assert sorted([equipa.id for equipa in evento.equipas]) == sorted([equipa_id_1, equipa_id_2])
    finally:
        _limpar_planeamento_teste()


def test_criacao_de_evento_para_todas_as_equipas_funciona():
    client = _criar_client()
    _fazer_login(client, "coordenador")
    _limpar_planeamento_teste()

    try:
        _criar_equipas_teste()

        response = client.post(
            "/planeamento-clube/eventos/novo",
            data={
                "tipo": "evento_clube",
                "titulo": TITULO_EVENTO_MANUAL,
                "descricao": "",
                "data_evento": "2025-09-05",
                "hora_inicio": "10:00",
                "hora_fim": "12:00",
                "planeamento_anual_id": "",
                "planeamento_mensal_id": "",
                "plano_semanal_id": "",
                "equipas_ids": [],
                "espaco_id": "",
                "treinador_id": "",
                "aplica_a_todas_equipas": "true",
                "observacoes": "",
            },
            follow_redirects=False,
        )

        assert response.status_code == 303
        evento = _obter_evento_manual()
        assert evento is not None
        assert evento.aplica_a_todas_equipas is True
        assert evento.equipas == []
    finally:
        _limpar_planeamento_teste()


def test_edicao_de_anual_funciona():
    client = _criar_client()
    _fazer_login(client, "admin")
    _limpar_planeamento_teste()

    try:
        client.post(
            "/planeamento-clube/anual/novo",
            data={
                "epoca": "2025/2026",
                "titulo": TITULO_ANUAL_TESTE,
                "data_inicio": "2025-09-01",
                "data_fim": "2026-06-30",
                "objetivos_gerais": "",
                "observacoes": "",
                "ativo": "true",
            },
            follow_redirects=False,
        )
        anual_id, _, _ = _obter_ids_por_titulos()
        assert anual_id is not None

        response = client.post(
            f"/planeamento-clube/anual/{anual_id}/editar",
            data={
                "epoca": "2025/2026",
                "titulo": TITULO_ANUAL_EDITADO,
                "data_inicio": "2025-09-02",
                "data_fim": "2026-06-28",
                "objetivos_gerais": "Objetivos revistos",
                "observacoes": "Observacoes revistas",
                "ativo": "false",
            },
            follow_redirects=False,
        )

        assert response.status_code == 303
        detalhe = client.get(f"/planeamento-clube/anual/{anual_id}", follow_redirects=False)
        assert detalhe.status_code == 200
        assert TITULO_ANUAL_EDITADO in detalhe.text
    finally:
        _limpar_planeamento_teste()


def test_edicao_de_mensal_funciona():
    client = _criar_client()
    _fazer_login(client, "coordenador")
    _limpar_planeamento_teste()

    try:
        _, mensal_id, _ = _criar_estrutura_semanal_teste(client)

        response = client.post(
            f"/planeamento-clube/mensal/{mensal_id}/editar",
            data={
                "ano": "2025",
                "mes": "10",
                "titulo": TITULO_MENSAL_EDITADO,
                "objetivos_mes": "Objetivos revistos",
                "observacoes": "Observacoes revistas",
                "estado": "rascunho",
            },
            follow_redirects=False,
        )

        assert response.status_code == 303
        detalhe = client.get(f"/planeamento-clube/mensal/{mensal_id}", follow_redirects=False)
        assert detalhe.status_code == 200
        assert TITULO_MENSAL_EDITADO in detalhe.text
    finally:
        _limpar_planeamento_teste()


def test_edicao_de_semanal_funciona():
    client = _criar_client()
    _fazer_login(client, "admin")
    _limpar_planeamento_teste()

    try:
        _, _, semanal_id = _criar_estrutura_semanal_teste(client)

        response = client.post(
            f"/planeamento-clube/semanal/{semanal_id}/editar",
            data={
                "titulo": TITULO_SEMANAL_EDITADO,
                "data_inicio": "2025-09-02",
                "data_fim": "2025-09-08",
                "observacoes": "Observacoes revistas",
                "estado": "rascunho",
            },
            follow_redirects=False,
        )

        assert response.status_code == 303
        detalhe = client.get(f"/planeamento-clube/semanal/{semanal_id}", follow_redirects=False)
        assert detalhe.status_code == 200
        assert TITULO_SEMANAL_EDITADO in detalhe.text
    finally:
        _limpar_planeamento_teste()


def test_eliminacao_de_anual_sem_dependencias_funciona():
    client = _criar_client()
    _fazer_login(client, "coordenador")
    _limpar_planeamento_teste()

    try:
        client.post(
            "/planeamento-clube/anual/novo",
            data={
                "epoca": "2025/2026",
                "titulo": TITULO_ANUAL_TESTE,
                "data_inicio": "2025-09-01",
                "data_fim": "2026-06-30",
                "objetivos_gerais": "",
                "observacoes": "",
                "ativo": "true",
            },
            follow_redirects=False,
        )
        anual_id, _, _ = _obter_ids_por_titulos()
        assert anual_id is not None

        response = client.post(f"/planeamento-clube/anual/{anual_id}/eliminar", follow_redirects=False)

        assert response.status_code == 303
        anual_id_depois, _, _ = _obter_ids_por_titulos()
        assert anual_id_depois is None
    finally:
        _limpar_planeamento_teste()


def test_eliminacao_de_anual_remove_hierarquia_com_mensais_e_semanais():
    from database import SessionLocal
    from models.planeamento_clube import PlaneamentoClubeAnual, PlaneamentoClubeMensal, PlanoSemanalClube

    client = _criar_client()
    _fazer_login(client, "coordenador")
    _limpar_planeamento_teste()

    try:
        anual_id, mensal_id, semanal_id = _criar_estrutura_semanal_teste(client)

        response = client.post(f"/planeamento-clube/anual/{anual_id}/eliminar", follow_redirects=False)

        assert response.status_code == 303
        assert response.headers["location"] == "/planeamento-clube/anual"

        db = SessionLocal()
        try:
            assert db.query(PlaneamentoClubeAnual).filter(PlaneamentoClubeAnual.id == anual_id).first() is None
            assert db.query(PlaneamentoClubeMensal).filter(PlaneamentoClubeMensal.id == mensal_id).first() is None
            assert db.query(PlanoSemanalClube).filter(PlanoSemanalClube.id == semanal_id).first() is None
        finally:
            db.close()
    finally:
        _limpar_planeamento_teste()


def test_eliminacao_de_mensal_bloqueia_com_dependencias():
    client = _criar_client()
    _fazer_login(client, "admin")
    _limpar_planeamento_teste()

    try:
        _, mensal_id, _ = _criar_estrutura_semanal_teste(client)

        response = client.post(f"/planeamento-clube/mensal/{mensal_id}/eliminar", follow_redirects=False)

        assert response.status_code == 303
        assert "erro=mensal_com_semanais" in response.headers["location"]
    finally:
        _limpar_planeamento_teste()


def test_eliminacao_de_semanal_remove_eventos_e_marcacoes_associadas():
    from database import SessionLocal
    from models.planeamento_clube import EventoPlaneamentoClube, PlanoSemanalClube

    client = _criar_client()
    _fazer_login(client, "coordenador")
    _limpar_planeamento_teste()

    try:
        anual_id, mensal_id, semanal_id = _criar_estrutura_semanal_teste(client)
        client.post(
            "/planeamento-clube/eventos/novo",
            data={
                "tipo": "evento_clube",
                "titulo": TITULO_EVENTO_MANUAL,
                "descricao": "",
                "data_evento": "2025-09-05",
                "hora_inicio": "10:00",
                "hora_fim": "12:00",
                "planeamento_anual_id": str(anual_id),
                "planeamento_mensal_id": str(mensal_id),
                "plano_semanal_id": str(semanal_id),
                "equipa_id": "",
                "treinador_id": "",
                "observacoes": "",
            },
            follow_redirects=False,
        )

        response = client.post(f"/planeamento-clube/semanal/{semanal_id}/eliminar", follow_redirects=False)

        assert response.status_code == 303
        assert response.headers["location"] == f"/planeamento-clube/mensal/{mensal_id}"

        db = SessionLocal()
        try:
            assert db.query(PlanoSemanalClube).filter(PlanoSemanalClube.id == semanal_id).first() is None
            assert db.query(EventoPlaneamentoClube).filter(
                EventoPlaneamentoClube.plano_semanal_id == semanal_id
            ).first() is None
        finally:
            db.close()
    finally:
        _limpar_planeamento_teste()


def test_eliminacao_de_espaco_bloqueia_se_tiver_atribuicoes():
    client = _criar_client()
    _fazer_login(client, "coordenador")
    _limpar_planeamento_teste()

    try:
        _, _, semanal_id = _criar_estrutura_semanal_teste(client)
        client.post(
            "/planeamento-clube/espacos/novo",
            data={
                "nome": NOME_ESPACO_TESTE,
                "tipo": "pavilhao",
                "localizacao": "Complexo Desportivo",
                "capacidade": "120",
                "ativo": "true",
                "observacoes": "",
            },
            follow_redirects=False,
        )
        espaco_id = _obter_espaco_por_nome(NOME_ESPACO_TESTE)
        client.post(
            f"/planeamento-clube/semanal/{semanal_id}/atribuicoes/nova",
            data={
                "espaco_id": str(espaco_id),
                "equipa_id": "",
                "evento_id": "",
                "data_atribuicao": "2025-09-03",
                "hora_inicio": "18:00",
                "hora_fim": "19:30",
                "tipo_ocupacao": "treino_equipa",
                "estado": "rascunho",
                "origem": "manual",
                "observacoes": "Reserva semanal de teste",
            },
            follow_redirects=False,
        )

        response = client.post(f"/planeamento-clube/espacos/{espaco_id}/eliminar", follow_redirects=False)

        assert response.status_code == 303
        assert "erro=espaco_com_atribuicoes" in response.headers["location"]
    finally:
        _limpar_planeamento_teste()


def test_criacao_de_atribuicao_funciona():
    client = _criar_client()
    _fazer_login(client, "coordenador")
    _limpar_planeamento_teste()

    try:
        _, _, semanal_id = _criar_estrutura_semanal_teste(client)
        _criar_suporte_eventos()
        client.post(
            "/planeamento-clube/espacos/novo",
            data={
                "nome": NOME_ESPACO_TESTE,
                "tipo": "pavilhao",
                "localizacao": "Complexo Desportivo",
                "capacidade": "120",
                "ativo": "true",
                "observacoes": "",
            },
            follow_redirects=False,
        )
        espaco_id = _obter_espaco_por_nome(NOME_ESPACO_TESTE)

        response = client.post(
            f"/planeamento-clube/semanal/{semanal_id}/atribuicoes/nova",
            data={
                "espaco_id": str(espaco_id),
                "equipa_id": "",
                "evento_id": "",
                "data_atribuicao": "2025-09-03",
                "hora_inicio": "18:00",
                "hora_fim": "19:30",
                "tipo_ocupacao": "treino_equipa",
                "estado": "rascunho",
                "origem": "manual",
                "observacoes": "Reserva semanal de teste",
            },
            follow_redirects=False,
        )

        assert response.status_code == 303
        atribuicao_id = _obter_atribuicao_por_espaco(espaco_id)
        assert atribuicao_id is not None

        detalhe = client.get(f"/planeamento-clube/atribuicoes/{atribuicao_id}", follow_redirects=False)
        assert detalhe.status_code == 200
        assert "Reserva semanal de teste" in detalhe.text
    finally:
        _limpar_planeamento_teste()


def test_edicao_de_atribuicao_funciona():
    client = _criar_client()
    _fazer_login(client, "admin")
    _limpar_planeamento_teste()

    try:
        _, _, semanal_id = _criar_estrutura_semanal_teste(client)
        client.post(
            "/planeamento-clube/espacos/novo",
            data={
                "nome": NOME_ESPACO_TESTE,
                "tipo": "pavilhao",
                "localizacao": "Complexo Desportivo",
                "capacidade": "120",
                "ativo": "true",
                "observacoes": "",
            },
            follow_redirects=False,
        )
        espaco_id = _obter_espaco_por_nome(NOME_ESPACO_TESTE)

        client.post(
            f"/planeamento-clube/semanal/{semanal_id}/atribuicoes/nova",
            data={
                "espaco_id": str(espaco_id),
                "equipa_id": "",
                "evento_id": "",
                "data_atribuicao": "2025-09-03",
                "hora_inicio": "18:00",
                "hora_fim": "19:30",
                "tipo_ocupacao": "treino_equipa",
                "estado": "rascunho",
                "origem": "manual",
                "observacoes": "Reserva semanal de teste",
            },
            follow_redirects=False,
        )
        atribuicao_id = _obter_atribuicao_por_espaco(espaco_id)
        assert atribuicao_id is not None

        response = client.post(
            f"/planeamento-clube/atribuicoes/{atribuicao_id}/editar",
            data={
                "espaco_id": str(espaco_id),
                "equipa_id": "",
                "evento_id": "",
                "data_atribuicao": "2025-09-03",
                "hora_inicio": "19:00",
                "hora_fim": "20:30",
                "tipo_ocupacao": "atividade",
                "estado": "publicado",
                "origem": "manual",
                "observacoes": "Reserva semanal editada",
            },
            follow_redirects=False,
        )

        assert response.status_code == 303
        detalhe = client.get(f"/planeamento-clube/atribuicoes/{atribuicao_id}", follow_redirects=False)
        assert detalhe.status_code == 200
        assert "Reserva semanal editada" in detalhe.text
        assert "publicado" in detalhe.text
    finally:
        _limpar_planeamento_teste()


def test_eliminacao_de_atribuicao_funciona():
    client = _criar_client()
    _fazer_login(client, "coordenador")
    _limpar_planeamento_teste()

    try:
        _, _, semanal_id = _criar_estrutura_semanal_teste(client)
        client.post(
            "/planeamento-clube/espacos/novo",
            data={
                "nome": NOME_ESPACO_TESTE,
                "tipo": "pavilhao",
                "localizacao": "Complexo Desportivo",
                "capacidade": "120",
                "ativo": "true",
                "observacoes": "",
            },
            follow_redirects=False,
        )
        espaco_id = _obter_espaco_por_nome(NOME_ESPACO_TESTE)

        client.post(
            f"/planeamento-clube/semanal/{semanal_id}/atribuicoes/nova",
            data={
                "espaco_id": str(espaco_id),
                "equipa_id": "",
                "evento_id": "",
                "data_atribuicao": "2025-09-03",
                "hora_inicio": "18:00",
                "hora_fim": "19:30",
                "tipo_ocupacao": "treino_equipa",
                "estado": "rascunho",
                "origem": "manual",
                "observacoes": "Reserva semanal de teste",
            },
            follow_redirects=False,
        )
        atribuicao_id = _obter_atribuicao_por_espaco(espaco_id)
        assert atribuicao_id is not None

        response = client.post(f"/planeamento-clube/atribuicoes/{atribuicao_id}/eliminar", follow_redirects=False)

        assert response.status_code == 303
        assert _obter_atribuicao_por_espaco(espaco_id) is None
    finally:
        _limpar_planeamento_teste()


def test_detecao_de_conflito_funciona():
    client = _criar_client()
    _fazer_login(client, "coordenador")
    _limpar_planeamento_teste()

    try:
        _, _, semanal_id = _criar_estrutura_semanal_teste(client)
        client.post(
            "/planeamento-clube/espacos/novo",
            data={
                "nome": NOME_ESPACO_TESTE,
                "tipo": "pavilhao",
                "localizacao": "Complexo Desportivo",
                "capacidade": "120",
                "ativo": "true",
                "observacoes": "",
            },
            follow_redirects=False,
        )
        espaco_id = _obter_espaco_por_nome(NOME_ESPACO_TESTE)

        client.post(
            f"/planeamento-clube/semanal/{semanal_id}/atribuicoes/nova",
            data={
                "espaco_id": str(espaco_id),
                "equipa_id": "",
                "evento_id": "",
                "data_atribuicao": "2025-09-03",
                "hora_inicio": "18:00",
                "hora_fim": "19:30",
                "tipo_ocupacao": "treino_equipa",
                "estado": "rascunho",
                "origem": "manual",
                "observacoes": "Reserva semanal de teste",
            },
            follow_redirects=False,
        )

        response = client.post(
            f"/planeamento-clube/semanal/{semanal_id}/atribuicoes/nova",
            data={
                "espaco_id": str(espaco_id),
                "equipa_id": "",
                "evento_id": "",
                "data_atribuicao": "2025-09-03",
                "hora_inicio": "19:00",
                "hora_fim": "20:00",
                "tipo_ocupacao": "atividade",
                "estado": "rascunho",
                "origem": "manual",
                "observacoes": "Conflito",
            },
            follow_redirects=False,
        )

        assert response.status_code == 400
        assert "Já existe uma atribuição activa para este espaço" in response.text
    finally:
        _limpar_planeamento_teste()


def test_detalhe_semanal_mostra_atribuicoes():
    client = _criar_client()
    _fazer_login(client, "coordenador")
    _limpar_planeamento_teste()

    try:
        _, _, semanal_id = _criar_estrutura_semanal_teste(client)
        client.post(
            "/planeamento-clube/espacos/novo",
            data={
                "nome": NOME_ESPACO_TESTE,
                "tipo": "pavilhao",
                "localizacao": "Complexo Desportivo",
                "capacidade": "120",
                "ativo": "true",
                "observacoes": "",
            },
            follow_redirects=False,
        )
        espaco_id = _obter_espaco_por_nome(NOME_ESPACO_TESTE)

        client.post(
            f"/planeamento-clube/semanal/{semanal_id}/atribuicoes/nova",
            data={
                "espaco_id": str(espaco_id),
                "equipa_id": "",
                "evento_id": "",
                "data_atribuicao": "2025-09-03",
                "hora_inicio": "18:00",
                "hora_fim": "19:30",
                "tipo_ocupacao": "treino_equipa",
                "estado": "publicado",
                "origem": "manual",
                "observacoes": "Reserva semanal de teste",
            },
            follow_redirects=False,
        )

        detalhe = client.get(f"/planeamento-clube/semanal/{semanal_id}", follow_redirects=False)

        assert detalhe.status_code == 200
        assert "Atribuições de Espaço" in detalhe.text
        assert NOME_ESPACO_TESTE in detalhe.text
    finally:
        _limpar_planeamento_teste()


def test_associacao_de_jogo_existente_funciona():
    client = _criar_client()
    _fazer_login(client, "coordenador")
    _limpar_planeamento_teste()

    try:
        equipa_id, jogo_id, _ = _criar_suporte_eventos()
        assert equipa_id is not None

        response = client.post(
            f"/planeamento-clube/eventos/jogo/{jogo_id}",
            data={
                "planeamento_anual_id": "",
                "planeamento_mensal_id": "",
                "plano_semanal_id": "",
                "observacoes": "Evento criado a partir de jogo",
            },
            follow_redirects=False,
        )

        assert response.status_code == 303
        evento_id = _obter_evento_por_jogo(jogo_id)
        assert evento_id is not None

        detalhe = client.get(f"/planeamento-clube/eventos/{evento_id}")
        assert detalhe.status_code == 200
        assert ADVERSARIO_JOGO_TESTE in detalhe.text
    finally:
        _limpar_planeamento_teste()


def test_associacao_de_atividade_existente_funciona():
    client = _criar_client()
    _fazer_login(client, "coordenador")
    _limpar_planeamento_teste()

    try:
        _, _, atividade_id = _criar_suporte_eventos()

        response = client.post(
            f"/planeamento-clube/eventos/atividade/{atividade_id}",
            data={
                "planeamento_anual_id": "",
                "planeamento_mensal_id": "",
                "plano_semanal_id": "",
                "observacoes": "Evento criado a partir de atividade",
            },
            follow_redirects=False,
        )

        assert response.status_code == 303
        evento_id = _obter_evento_por_atividade(atividade_id)
        assert evento_id is not None

        detalhe = client.get(f"/planeamento-clube/eventos/{evento_id}")
        assert detalhe.status_code == 200
        assert TITULO_ATIVIDADE_TESTE in detalhe.text
    finally:
        _limpar_planeamento_teste()


def test_edicao_de_evento_funciona():
    client = _criar_client()
    _fazer_login(client, "admin")
    _limpar_planeamento_teste()

    try:
        client.post(
            "/planeamento-clube/anual/novo",
            data={
                "epoca": "2025/2026",
                "titulo": TITULO_ANUAL_TESTE,
                "data_inicio": "2025-09-01",
                "data_fim": "2026-06-30",
                "objetivos_gerais": "",
                "observacoes": "",
                "ativo": "true",
            },
            follow_redirects=False,
        )
        anual_id, _, _, _ = _obter_ids_planeamento_teste()

        client.post(
            "/planeamento-clube/eventos/novo",
            data={
                "tipo": "evento_clube",
                "titulo": TITULO_EVENTO_MANUAL,
                "descricao": "",
                "data_evento": "2025-09-05",
                "hora_inicio": "10:00",
                "hora_fim": "12:00",
                "planeamento_anual_id": str(anual_id),
                "planeamento_mensal_id": "",
                "plano_semanal_id": "",
                "equipa_id": "",
                "treinador_id": "",
                "observacoes": "",
            },
            follow_redirects=False,
        )
        _, _, _, evento_id = _obter_ids_planeamento_teste()

        response = client.post(
            f"/planeamento-clube/eventos/{evento_id}/editar",
            data={
                "tipo": "evento_clube",
                "titulo": TITULO_EVENTO_EDITADO,
                "descricao": "Descricao editada",
                "data_evento": "2025-09-06",
                "hora_inicio": "11:00",
                "hora_fim": "13:00",
                "planeamento_anual_id": str(anual_id),
                "planeamento_mensal_id": "",
                "plano_semanal_id": "",
                "equipa_id": "",
                "treinador_id": "",
                "observacoes": "Observacoes editadas",
            },
            follow_redirects=False,
        )

        assert response.status_code == 303
        detalhe = client.get(f"/planeamento-clube/eventos/{evento_id}")
        assert TITULO_EVENTO_EDITADO in detalhe.text
    finally:
        _limpar_planeamento_teste()


def test_edicao_de_evento_actualiza_espaco_e_equipas():
    client = _criar_client()
    _fazer_login(client, "admin")
    _limpar_planeamento_teste()

    try:
        equipa_id_1, equipa_id_2 = _criar_equipas_teste()
        client.post(
            "/planeamento-clube/espacos/novo",
            data={
                "nome": NOME_ESPACO_TESTE,
                "tipo": "pavilhao",
                "localizacao": "Complexo Desportivo",
                "capacidade": "120",
                "ativo": "true",
                "observacoes": "",
            },
            follow_redirects=False,
        )
        espaco_id = _obter_espaco_por_nome(NOME_ESPACO_TESTE)

        client.post(
            "/planeamento-clube/eventos/novo",
            data={
                "tipo": "evento_clube",
                "titulo": TITULO_EVENTO_MANUAL,
                "descricao": "",
                "data_evento": "2025-09-05",
                "hora_inicio": "10:00",
                "hora_fim": "12:00",
                "planeamento_anual_id": "",
                "planeamento_mensal_id": "",
                "plano_semanal_id": "",
                "equipas_ids": [str(equipa_id_1)],
                "espaco_id": "",
                "treinador_id": "",
                "aplica_a_todas_equipas": "false",
                "observacoes": "",
            },
            follow_redirects=False,
        )
        evento = _obter_evento_manual()
        assert evento is not None

        response = client.post(
            f"/planeamento-clube/eventos/{evento.id}/editar",
            data={
                "tipo": "evento_clube",
                "titulo": TITULO_EVENTO_EDITADO,
                "descricao": "Descricao editada",
                "data_evento": "2025-09-06",
                "hora_inicio": "11:00",
                "hora_fim": "13:00",
                "planeamento_anual_id": "",
                "planeamento_mensal_id": "",
                "plano_semanal_id": "",
                "equipas_ids": [str(equipa_id_1), str(equipa_id_2)],
                "espaco_id": str(espaco_id),
                "treinador_id": "",
                "aplica_a_todas_equipas": "false",
                "observacoes": "Observacoes editadas",
            },
            follow_redirects=False,
        )

        assert response.status_code == 303
        evento_actualizado = _obter_evento_manual()
        assert evento_actualizado is not None
        assert evento_actualizado.espaco_id == espaco_id
        assert sorted([equipa.id for equipa in evento_actualizado.equipas]) == sorted([equipa_id_1, equipa_id_2])
    finally:
        _limpar_planeamento_teste()


def test_eliminacao_de_evento_mantem_jogo_e_atividade():
    client = _criar_client()
    _fazer_login(client, "coordenador")
    _limpar_planeamento_teste()

    try:
        _, jogo_id, atividade_id = _criar_suporte_eventos()

        client.post(
            f"/planeamento-clube/eventos/jogo/{jogo_id}",
            data={"planeamento_anual_id": "", "planeamento_mensal_id": "", "plano_semanal_id": "", "observacoes": ""},
            follow_redirects=False,
        )
        client.post(
            f"/planeamento-clube/eventos/atividade/{atividade_id}",
            data={"planeamento_anual_id": "", "planeamento_mensal_id": "", "plano_semanal_id": "", "observacoes": ""},
            follow_redirects=False,
        )

        evento_jogo_id = _obter_evento_por_jogo(jogo_id)
        evento_atividade_id = _obter_evento_por_atividade(atividade_id)

        response_jogo = client.post(f"/planeamento-clube/eventos/{evento_jogo_id}/eliminar", follow_redirects=False)
        response_atividade = client.post(f"/planeamento-clube/eventos/{evento_atividade_id}/eliminar", follow_redirects=False)

        assert response_jogo.status_code == 303
        assert response_atividade.status_code == 303

        from database import SessionLocal
        from models.atividade import Atividade
        from models.jogo import Jogo

        db = SessionLocal()
        try:
            assert db.query(Jogo).filter(Jogo.id == jogo_id).first() is not None
            assert db.query(Atividade).filter(Atividade.id == atividade_id).first() is not None
        finally:
            db.close()
    finally:
        _limpar_planeamento_teste()


def test_evento_para_todas_as_equipas_aparece_no_contexto_da_equipa():
    client = _criar_client()
    _fazer_login(client, "coordenador")
    _limpar_planeamento_teste()

    try:
        equipa_id_1, equipa_id_2 = _criar_equipas_teste()
        client.post(
            "/planeamento-clube/eventos/novo",
            data={
                "tipo": "evento_clube",
                "titulo": TITULO_EVENTO_MANUAL,
                "descricao": "",
                "data_evento": "2025-09-05",
                "hora_inicio": "10:00",
                "hora_fim": "12:00",
                "planeamento_anual_id": "",
                "planeamento_mensal_id": "",
                "plano_semanal_id": "",
                "equipas_ids": [],
                "espaco_id": "",
                "treinador_id": "",
                "aplica_a_todas_equipas": "true",
                "observacoes": "",
            },
            follow_redirects=False,
        )

        detalhe_equipa_1 = client.get(f"/equipas/{equipa_id_1}/eventos", follow_redirects=False)
        detalhe_equipa_2 = client.get(f"/equipas/{equipa_id_2}/eventos", follow_redirects=False)

        assert detalhe_equipa_1.status_code == 200
        assert detalhe_equipa_2.status_code == 200
        assert TITULO_EVENTO_MANUAL in detalhe_equipa_1.text
        assert TITULO_EVENTO_MANUAL in detalhe_equipa_2.text
    finally:
        _limpar_planeamento_teste()


def test_evento_associado_a_uma_equipa_aparece_apenas_nessa_equipa():
    client = _criar_client()
    _fazer_login(client, "coordenador")
    _limpar_planeamento_teste()

    try:
        equipa_id_1, equipa_id_2 = _criar_equipas_teste()
        client.post(
            "/planeamento-clube/eventos/novo",
            data={
                "tipo": "evento_clube",
                "titulo": TITULO_EVENTO_MANUAL,
                "descricao": "",
                "data_evento": "2025-09-05",
                "hora_inicio": "10:00",
                "hora_fim": "12:00",
                "planeamento_anual_id": "",
                "planeamento_mensal_id": "",
                "plano_semanal_id": "",
                "equipas_ids": [str(equipa_id_1)],
                "espaco_id": "",
                "treinador_id": "",
                "aplica_a_todas_equipas": "false",
                "observacoes": "",
            },
            follow_redirects=False,
        )

        detalhe_equipa_1 = client.get(f"/equipas/{equipa_id_1}/eventos", follow_redirects=False)
        detalhe_equipa_2 = client.get(f"/equipas/{equipa_id_2}/eventos", follow_redirects=False)

        assert detalhe_equipa_1.status_code == 200
        assert detalhe_equipa_2.status_code == 200
        assert TITULO_EVENTO_MANUAL in detalhe_equipa_1.text
        assert TITULO_EVENTO_MANUAL not in detalhe_equipa_2.text
    finally:
        _limpar_planeamento_teste()


def test_detalhe_mensal_apresenta_calendario_e_evento_no_dia_certo():
    client = _criar_client()
    _fazer_login(client, "coordenador")
    _limpar_planeamento_teste()

    try:
        anual_id, mensal_id, _ = _criar_estrutura_semanal_teste(client)
        client.post(
            "/planeamento-clube/eventos/novo",
            data={
                "tipo": "evento_clube",
                "titulo": TITULO_EVENTO_MANUAL,
                "descricao": "",
                "data_evento": "2025-09-05",
                "hora_inicio": "10:00",
                "hora_fim": "12:00",
                "planeamento_anual_id": str(anual_id),
                "planeamento_mensal_id": str(mensal_id),
                "plano_semanal_id": "",
                "equipas_ids": [],
                "espaco_id": "",
                "treinador_id": "",
                "aplica_a_todas_equipas": "false",
                "observacoes": "",
            },
            follow_redirects=False,
        )

        detalhe = client.get(f"/planeamento-clube/mensal/{mensal_id}", follow_redirects=False)

        assert detalhe.status_code == 200
        assert "Calendário Mensal" in detalhe.text
        assert TITULO_EVENTO_MANUAL in detalhe.text
        assert "5" in detalhe.text
    finally:
        _limpar_planeamento_teste()


def test_detalhe_semanal_apresenta_calendario_e_evento_no_dia_certo():
    client = _criar_client()
    _fazer_login(client, "coordenador")
    _limpar_planeamento_teste()

    try:
        anual_id, mensal_id, semanal_id = _criar_estrutura_semanal_teste(client)
        client.post(
            "/planeamento-clube/eventos/novo",
            data={
                "tipo": "evento_clube",
                "titulo": TITULO_EVENTO_MANUAL,
                "descricao": "",
                "data_evento": "2025-09-03",
                "hora_inicio": "10:00",
                "hora_fim": "12:00",
                "planeamento_anual_id": str(anual_id),
                "planeamento_mensal_id": str(mensal_id),
                "plano_semanal_id": str(semanal_id),
                "equipas_ids": [],
                "espaco_id": "",
                "treinador_id": "",
                "aplica_a_todas_equipas": "false",
                "observacoes": "",
            },
            follow_redirects=False,
        )

        detalhe = client.get(f"/planeamento-clube/semanal/{semanal_id}", follow_redirects=False)

        assert detalhe.status_code == 200
        assert "Calendário Semanal" in detalhe.text
        assert TITULO_EVENTO_MANUAL in detalhe.text
        assert "2025-09-03" in detalhe.text
    finally:
        _limpar_planeamento_teste()


def test_treinador_bloqueado_na_edicao_e_eliminacao():
    client = _criar_client()
    _limpar_planeamento_teste()

    try:
        _fazer_login(client, "coordenador")
        client.post(
            "/planeamento-clube/anual/novo",
            data={
                "epoca": "2025/2026",
                "titulo": TITULO_ANUAL_TESTE,
                "data_inicio": "2025-09-01",
                "data_fim": "2026-06-30",
                "objetivos_gerais": "",
                "observacoes": "",
                "ativo": "true",
            },
            follow_redirects=False,
        )
        anual_id, _, _, _ = _obter_ids_planeamento_teste()
        client.post(
            "/planeamento-clube/eventos/novo",
            data={
                "tipo": "evento_clube",
                "titulo": TITULO_EVENTO_MANUAL,
                "descricao": "",
                "data_evento": "2025-09-05",
                "hora_inicio": "",
                "hora_fim": "",
                "planeamento_anual_id": str(anual_id),
                "planeamento_mensal_id": "",
                "plano_semanal_id": "",
                "equipa_id": "",
                "treinador_id": "",
                "observacoes": "",
            },
            follow_redirects=False,
        )
        _, _, _, evento_id = _obter_ids_planeamento_teste()

        client_treinador = _criar_client()
        _fazer_login(client_treinador, "treinador")

        response_editar = client_treinador.get(f"/planeamento-clube/eventos/{evento_id}/editar", follow_redirects=False)
        response_eliminar = client_treinador.post(f"/planeamento-clube/eventos/{evento_id}/eliminar", follow_redirects=False)

        assert response_editar.status_code in [302, 307]
        assert response_editar.headers["location"] == "/dashboard"
        assert response_eliminar.status_code in [302, 307]
        assert response_eliminar.headers["location"] == "/dashboard"
    finally:
        _limpar_planeamento_teste()


def test_treinador_nao_consegue_editar_ou_eliminar_planeamentos():
    client = _criar_client()
    _limpar_planeamento_teste()

    try:
        _fazer_login(client, "coordenador")
        anual_id, mensal_id, semanal_id = _criar_estrutura_semanal_teste(client)

        client_treinador = _criar_client()
        _fazer_login(client_treinador, "treinador")

        response_anual_editar = client_treinador.get(f"/planeamento-clube/anual/{anual_id}/editar", follow_redirects=False)
        response_mensal_eliminar = client_treinador.post(f"/planeamento-clube/mensal/{mensal_id}/eliminar", follow_redirects=False)
        response_semanal_editar = client_treinador.get(f"/planeamento-clube/semanal/{semanal_id}/editar", follow_redirects=False)

        assert response_anual_editar.status_code in [302, 307]
        assert response_anual_editar.headers["location"] == "/dashboard"
        assert response_mensal_eliminar.status_code in [302, 307]
        assert response_mensal_eliminar.headers["location"] == "/dashboard"
        assert response_semanal_editar.status_code in [302, 307]
        assert response_semanal_editar.headers["location"] == "/dashboard"
    finally:
        _limpar_planeamento_teste()


def test_administrador_consegue_sincronizar_plano_semanal():
    client = _criar_client()
    _limpar_planeamento_teste()

    try:
        contexto = _criar_contexto_sincronizacao()
        _fazer_login(client, "admin")

        response = client.post(
            f"/planeamento-clube/semanal/{contexto['semanal_id']}/sincronizar",
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert response.headers["location"].startswith(f"/planeamento-clube/semanal/{contexto['semanal_id']}?sincronizado=1")
    finally:
        _limpar_planeamento_teste()


def test_coordenador_consegue_sincronizar_plano_semanal():
    client = _criar_client()
    _limpar_planeamento_teste()

    try:
        contexto = _criar_contexto_sincronizacao()
        _fazer_login(client, "coordenador")

        response = client.post(
            f"/planeamento-clube/semanal/{contexto['semanal_id']}/sincronizar",
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert response.headers["location"].startswith(f"/planeamento-clube/semanal/{contexto['semanal_id']}?sincronizado=1")
    finally:
        _limpar_planeamento_teste()


def test_treinador_nao_consegue_sincronizar_plano_semanal():
    client = _criar_client()
    _limpar_planeamento_teste()

    try:
        contexto = _criar_contexto_sincronizacao()
        _fazer_login(client, "treinador")

        response = client.post(
            f"/planeamento-clube/semanal/{contexto['semanal_id']}/sincronizar",
            follow_redirects=False,
        )

        assert response.status_code in [302, 307]
        assert response.headers["location"] == "/dashboard"
    finally:
        _limpar_planeamento_teste()


def test_sincronizacao_cria_sessoes_sem_duplicar_nas_equipas_corretas():
    from database import SessionLocal
    from models.planeamento import Macrociclo, Mesociclo, Microciclo, SessaoTreino

    client = _criar_client()
    _limpar_planeamento_teste()

    try:
        contexto = _criar_contexto_sincronizacao()
        _fazer_login(client, "coordenador")

        response_1 = client.post(
            f"/planeamento-clube/semanal/{contexto['semanal_id']}/sincronizar",
            follow_redirects=False,
        )
        response_2 = client.post(
            f"/planeamento-clube/semanal/{contexto['semanal_id']}/sincronizar",
            follow_redirects=False,
        )

        assert response_1.status_code == 303
        assert response_2.status_code == 303

        db = SessionLocal()
        try:
            sessoes = db.query(SessaoTreino).filter(
                SessaoTreino.plano_semanal_clube_id == contexto["semanal_id"],
                SessaoTreino.ativa == True,
            ).all()

            test_team_ids = {contexto["equipa_1_id"], contexto["equipa_2_id"]}
            sessoes_alvo = [
                s for s in sessoes
                if s.microciclo.mesociclo.macrociclo.equipa_id in test_team_ids
            ]
            assert len(sessoes_alvo) == 5

            equipas_por_evento = {}
            for sessao in sessoes_alvo:
                equipa_id = sessao.microciclo.mesociclo.macrociclo.equipa_id
                equipas_por_evento.setdefault(sessao.evento_planeamento_clube_id, set()).add(equipa_id)
                assert sessao.origem == "planeamento_global"
                assert sessao.sincronizada is True
                assert sessao.alterada_manual is False

            assert equipas_por_evento[contexto["evento_unico_id"]] == {contexto["equipa_1_id"]}
            assert equipas_por_evento[contexto["evento_multi_id"]] == {contexto["equipa_1_id"], contexto["equipa_2_id"]}
            assert equipas_por_evento[contexto["evento_global_id"]] == {contexto["equipa_1_id"], contexto["equipa_2_id"]}
        finally:
            db.close()
    finally:
        _limpar_planeamento_teste()


def test_sincronizacao_cria_microciclos_automaticamente_quando_nao_existem():
    from database import SessionLocal
    from models.planeamento import Macrociclo, Mesociclo, Microciclo, SessaoTreino

    client = _criar_client()
    _limpar_planeamento_teste()

    try:
        contexto = _criar_contexto_sincronizacao(criar_microciclos=False)
        _fazer_login(client, "coordenador")

        response = client.post(
            f"/planeamento-clube/semanal/{contexto['semanal_id']}/sincronizar",
            follow_redirects=False,
        )

        assert response.status_code == 303

        db = SessionLocal()
        try:
            microciclos = db.query(Microciclo).join(Mesociclo).join(Macrociclo).filter(
                Macrociclo.equipa_id.in_([contexto["equipa_1_id"], contexto["equipa_2_id"]])
            ).order_by(Macrociclo.equipa_id.asc(), Microciclo.data_inicio.asc()).all()
            assert len(microciclos) == 2
            for microciclo in microciclos:
                assert microciclo.data_inicio == date.fromisoformat("2025-09-08")
                assert microciclo.data_fim == date.fromisoformat("2025-09-14")

            sessoes = db.query(SessaoTreino).filter(
                SessaoTreino.plano_semanal_clube_id == contexto["semanal_id"]
            ).all()
            test_team_ids = {contexto["equipa_1_id"], contexto["equipa_2_id"]}
            sessoes_alvo = [
                s for s in sessoes
                if s.microciclo and s.microciclo.mesociclo and s.microciclo.mesociclo.macrociclo
                and s.microciclo.mesociclo.macrociclo.equipa_id in test_team_ids
            ]
            assert len(sessoes_alvo) == 5
            assert all(sessao.microciclo_id is not None for sessao in sessoes_alvo)
        finally:
            db.close()
    finally:
        _limpar_planeamento_teste()


def test_sincronizacao_nao_duplica_microciclos_automaticos_em_sincronizacoes_repetidas():
    from database import SessionLocal
    from models.planeamento import Macrociclo, Mesociclo, Microciclo

    client = _criar_client()
    _limpar_planeamento_teste()

    try:
        contexto = _criar_contexto_sincronizacao(criar_microciclos=False)
        _fazer_login(client, "admin")

        response_1 = client.post(
            f"/planeamento-clube/semanal/{contexto['semanal_id']}/sincronizar",
            follow_redirects=False,
        )
        response_2 = client.post(
            f"/planeamento-clube/semanal/{contexto['semanal_id']}/sincronizar",
            follow_redirects=False,
        )

        assert response_1.status_code == 303
        assert response_2.status_code == 303

        db = SessionLocal()
        try:
            microciclos = db.query(Microciclo).join(Mesociclo).join(Macrociclo).filter(
                Macrociclo.equipa_id.in_([contexto["equipa_1_id"], contexto["equipa_2_id"]])
            ).all()
            assert len(microciclos) == 2
        finally:
            db.close()
    finally:
        _limpar_planeamento_teste()


def test_sincronizacao_reutiliza_microciclo_existente_da_mesma_semana():
    from database import SessionLocal
    from models.planeamento import Macrociclo, Mesociclo, Microciclo, SessaoTreino

    client = _criar_client()
    _limpar_planeamento_teste()

    try:
        contexto = _criar_contexto_sincronizacao()
        _fazer_login(client, "coordenador")

        response = client.post(
            f"/planeamento-clube/semanal/{contexto['semanal_id']}/sincronizar",
            follow_redirects=False,
        )

        assert response.status_code == 303

        db = SessionLocal()
        try:
            microciclos = db.query(Microciclo).join(Mesociclo).join(Macrociclo).filter(
                Macrociclo.equipa_id.in_([contexto["equipa_1_id"], contexto["equipa_2_id"]])
            ).all()
            assert len(microciclos) == 2

            sessao = db.query(SessaoTreino).filter(
                SessaoTreino.evento_planeamento_clube_id == contexto["evento_unico_id"],
                SessaoTreino.origem == "planeamento_global",
            ).first()
            assert sessao is not None
            assert sessao.microciclo.data_inicio == date.fromisoformat("2025-09-08")
            assert sessao.microciclo.data_fim == date.fromisoformat("2025-09-14")
        finally:
            db.close()
    finally:
        _limpar_planeamento_teste()


def test_sincronizacao_reassocia_sessao_para_microciclo_da_nova_semana():
    from database import SessionLocal
    from models.planeamento import SessaoTreino
    from models.planeamento_clube import EventoPlaneamentoClube

    client = _criar_client()
    _limpar_planeamento_teste()

    try:
        contexto = _criar_contexto_sincronizacao()
        _fazer_login(client, "admin")

        client.post(
            f"/planeamento-clube/semanal/{contexto['semanal_id']}/sincronizar",
            follow_redirects=False,
        )

        db = SessionLocal()
        try:
            sessao = db.query(SessaoTreino).filter(
                SessaoTreino.evento_planeamento_clube_id == contexto["evento_unico_id"],
                SessaoTreino.origem == "planeamento_global",
            ).first()
            evento = db.query(EventoPlaneamentoClube).filter(
                EventoPlaneamentoClube.id == contexto["evento_unico_id"]
            ).first()

            assert sessao is not None
            assert evento is not None

            microciclo_inicial_id = sessao.microciclo_id
            evento.data = date.fromisoformat("2025-09-16")
            db.commit()
        finally:
            db.close()

        client.post(
            f"/planeamento-clube/semanal/{contexto['semanal_id']}/sincronizar",
            follow_redirects=False,
        )

        db = SessionLocal()
        try:
            sessao = db.query(SessaoTreino).filter(
                SessaoTreino.evento_planeamento_clube_id == contexto["evento_unico_id"],
                SessaoTreino.origem == "planeamento_global",
            ).first()
            assert sessao is not None
            assert sessao.microciclo_id != microciclo_inicial_id
            assert sessao.microciclo.data_inicio == date.fromisoformat("2025-09-15")
            assert sessao.microciclo.data_fim == date.fromisoformat("2025-09-21")
        finally:
            db.close()
    finally:
        _limpar_planeamento_teste()


def test_sincronizacao_atualiza_sessao_existente_nao_alterada_manual():
    from database import SessionLocal
    from models.planeamento import SessaoTreino
    from models.planeamento_clube import EventoPlaneamentoClube

    client = _criar_client()
    _limpar_planeamento_teste()

    try:
        contexto = _criar_contexto_sincronizacao()
        _fazer_login(client, "admin")

        client.post(
            f"/planeamento-clube/semanal/{contexto['semanal_id']}/sincronizar",
            follow_redirects=False,
        )

        db = SessionLocal()
        try:
            sessao = db.query(SessaoTreino).filter(
                SessaoTreino.evento_planeamento_clube_id == contexto["evento_unico_id"],
                SessaoTreino.origem == "planeamento_global",
            ).first()
            evento = db.query(EventoPlaneamentoClube).filter(
                EventoPlaneamentoClube.id == contexto["evento_unico_id"]
            ).first()

            assert sessao is not None
            assert evento is not None

            sessao_id = sessao.id
            evento.data = date.fromisoformat("2025-09-12")
            evento.observacoes = "Sessão revista pelo planeamento global"
            db.commit()
        finally:
            db.close()

        client.post(
            f"/planeamento-clube/semanal/{contexto['semanal_id']}/sincronizar",
            follow_redirects=False,
        )

        db = SessionLocal()
        try:
            sessao = db.query(SessaoTreino).filter(SessaoTreino.id == sessao_id).first()
            assert sessao is not None
            assert sessao.data == date.fromisoformat("2025-09-12")
            assert "Sessão revista pelo planeamento global" in (sessao.reflexao or "")
            assert sessao.sincronizada is True
            assert sessao.alterada_manual is False
            assert sessao.ativa is True
        finally:
            db.close()
    finally:
        _limpar_planeamento_teste()


def test_sincronizacao_ignora_sessao_de_outra_origem_com_mesmo_evento():
    from database import SessionLocal
    from models.planeamento import Macrociclo, Mesociclo, Microciclo, SessaoTreino

    client = _criar_client()
    _limpar_planeamento_teste()

    try:
        contexto = _criar_contexto_sincronizacao()
        _fazer_login(client, "coordenador")

        db = SessionLocal()
        try:
            microciclo = db.query(Microciclo).join(Mesociclo).join(Macrociclo).filter(
                Macrociclo.equipa_id == contexto["equipa_1_id"]
            ).first()
            assert microciclo is not None

            sessao_manual = SessaoTreino(
                data=date.fromisoformat("2025-09-09"),
                local="Sessão manual pré-existente",
                numero_treino=99,
                volume_minutos=75,
                intensidade_rpe=6.0,
                e_jogo=False,
                reflexao="Sessão criada manualmente",
                origem="manual",
                sincronizada=False,
                alterada_manual=False,
                ativa=True,
                microciclo_id=microciclo.id,
                evento_planeamento_clube_id=contexto["evento_unico_id"],
            )
            db.add(sessao_manual)
            db.commit()
            db.refresh(sessao_manual)
            sessao_manual_id = sessao_manual.id
        finally:
            db.close()

        response = client.post(
            f"/planeamento-clube/semanal/{contexto['semanal_id']}/sincronizar",
            follow_redirects=False,
        )

        assert response.status_code == 303

        db = SessionLocal()
        try:
            sessoes = db.query(SessaoTreino).join(Microciclo).join(Mesociclo).join(Macrociclo).filter(
                SessaoTreino.evento_planeamento_clube_id == contexto["evento_unico_id"],
                Macrociclo.equipa_id == contexto["equipa_1_id"],
            ).order_by(SessaoTreino.id.asc()).all()

            assert len(sessoes) == 2

            sessao_manual = next(sessao for sessao in sessoes if sessao.id == sessao_manual_id)
            sessao_global = next(sessao for sessao in sessoes if sessao.id != sessao_manual_id)

            assert sessao_manual.origem == "manual"
            assert sessao_manual.local == "Sessão manual pré-existente"
            assert sessao_global.origem == "planeamento_global"
            assert sessao_global.plano_semanal_clube_id == contexto["semanal_id"]
            assert sessao_global.sincronizada is True
            assert sessao_global.alterada_manual is False
        finally:
            db.close()
    finally:
        _limpar_planeamento_teste()


def test_sincronizacao_nao_sobrescreve_sessao_alterada_manual():
    from database import SessionLocal
    from models.planeamento import SessaoTreino
    from models.planeamento_clube import EventoPlaneamentoClube

    client = _criar_client()
    _limpar_planeamento_teste()

    try:
        contexto = _criar_contexto_sincronizacao()
        _fazer_login(client, "admin")

        client.post(f"/planeamento-clube/semanal/{contexto['semanal_id']}/sincronizar", follow_redirects=False)

        db = SessionLocal()
        try:
            sessao = db.query(SessaoTreino).filter(
                SessaoTreino.evento_planeamento_clube_id == contexto["evento_unico_id"]
            ).first()
            evento = db.query(EventoPlaneamentoClube).filter(
                EventoPlaneamentoClube.id == contexto["evento_unico_id"]
            ).first()

            sessao.local = "Local Ajustado Manualmente"
            sessao.alterada_manual = True
            sessao.sincronizada = False
            evento.espaco_id = None
            evento.observacoes = "Observação alterada no evento"
            db.commit()
        finally:
            db.close()

        client.post(f"/planeamento-clube/semanal/{contexto['semanal_id']}/sincronizar", follow_redirects=False)

        db = SessionLocal()
        try:
            sessao = db.query(SessaoTreino).filter(
                SessaoTreino.evento_planeamento_clube_id == contexto["evento_unico_id"]
            ).first()
            assert sessao.local == "Local Ajustado Manualmente"
            assert sessao.alterada_manual is True
            assert sessao.sincronizada is False
        finally:
            db.close()
    finally:
        _limpar_planeamento_teste()


def test_edicao_normal_da_equipa_marca_sessao_global_como_alterada_manual():
    from database import SessionLocal
    from models.planeamento import SessaoTreino
    from models.treino import PlanoTreino

    client = _criar_client()
    _limpar_planeamento_teste()

    try:
        contexto = _criar_contexto_sincronizacao()
        _fazer_login(client, "admin")

        client.post(
            f"/planeamento-clube/semanal/{contexto['semanal_id']}/sincronizar",
            follow_redirects=False,
        )

        db = SessionLocal()
        try:
            sessao = db.query(SessaoTreino).filter(
                SessaoTreino.evento_planeamento_clube_id == contexto["evento_unico_id"],
                SessaoTreino.origem == "planeamento_global",
            ).first()
            assert sessao is not None
            sessao_id = sessao.id
        finally:
            db.close()

        resposta_pagina = client.get(f"/treino/sessoes/{sessao_id}", follow_redirects=False)
        assert resposta_pagina.status_code == 200

        db = SessionLocal()
        try:
            plano = db.query(PlanoTreino).filter(PlanoTreino.sessao_id == sessao_id).first()
            assert plano is not None
            plano_id = plano.id
        finally:
            db.close()

        response = client.post(
            f"/treino/planos/{plano_id}/cabecalho",
            data={
                "hora_inicio": "18:30",
                "escalao": "U16",
                "objectivos": "Ajuste manual do plano",
            },
            follow_redirects=False,
        )

        assert response.status_code == 303

        db = SessionLocal()
        try:
            sessao = db.query(SessaoTreino).filter(SessaoTreino.id == sessao_id).first()
            assert sessao is not None
            assert sessao.origem == "planeamento_global"
            assert sessao.alterada_manual is True
            assert sessao.sincronizada is False
        finally:
            db.close()
    finally:
        _limpar_planeamento_teste()


def test_detalhe_semanal_mostra_metadados_e_feedback_da_ultima_sincronizacao():
    from database import SessionLocal
    from models.planeamento_clube import PlanoSemanalClube

    client = _criar_client()
    _limpar_planeamento_teste()

    try:
        contexto = _criar_contexto_sincronizacao()
        _fazer_login(client, "admin")

        response = client.post(
            f"/planeamento-clube/semanal/{contexto['semanal_id']}/sincronizar",
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert "Sincronização concluída" in response.text
        assert "Resumo da última sincronização" in response.text
        assert "Sincronizado por:" in response.text
        assert "admin" in response.text

        db = SessionLocal()
        try:
            semanal = db.query(PlanoSemanalClube).filter(PlanoSemanalClube.id == contexto["semanal_id"]).first()
            assert semanal is not None
            assert semanal.ultima_sincronizacao_em is not None
            assert semanal.ultima_sincronizacao_por == "admin"
            assert semanal.ultima_sincronizacao_resumo is not None
            assert "Sincronização concluída:" in semanal.ultima_sincronizacao_resumo
        finally:
            db.close()
    finally:
        _limpar_planeamento_teste()


def test_detalhe_microciclo_mostra_origem_estado_e_sessoes_desativadas():
    from database import SessionLocal
    from models.planeamento import Macrociclo, Mesociclo, Microciclo, SessaoTreino

    client = _criar_client()
    _limpar_planeamento_teste()

    try:
        contexto = _criar_contexto_sincronizacao()
        _fazer_login(client, "coordenador")

        client.post(
            f"/planeamento-clube/semanal/{contexto['semanal_id']}/sincronizar",
            follow_redirects=False,
        )

        db = SessionLocal()
        try:
            microciclo = db.query(Microciclo).join(Mesociclo).join(Macrociclo).filter(
                Macrociclo.equipa_id == contexto["equipa_1_id"]
            ).first()
            assert microciclo is not None

            sessao_alterada = db.query(SessaoTreino).filter(
                SessaoTreino.evento_planeamento_clube_id == contexto["evento_unico_id"]
            ).first()
            sessao_desatualizada = db.query(SessaoTreino).filter(
                SessaoTreino.evento_planeamento_clube_id == contexto["evento_multi_id"],
                SessaoTreino.microciclo_id == microciclo.id,
            ).first()
            sessao_desativada = db.query(SessaoTreino).filter(
                SessaoTreino.evento_planeamento_clube_id == contexto["evento_global_id"],
                SessaoTreino.microciclo_id == microciclo.id,
            ).first()

            assert sessao_alterada is not None
            assert sessao_desatualizada is not None
            assert sessao_desativada is not None

            sessao_alterada.alterada_manual = True
            sessao_alterada.sincronizada = False
            sessao_desatualizada.alterada_manual = False
            sessao_desatualizada.sincronizada = False
            sessao_desativada.ativa = False
            sessao_desativada.sincronizada = False
            db.commit()
            microciclo_id = microciclo.id
        finally:
            db.close()

        response = client.get(f"/planeamento/microciclos/{microciclo_id}", follow_redirects=False)

        assert response.status_code == 200
        assert "Planeamento Global do Clube" in response.text
        assert "Plano Semanal do Clube" in response.text
        assert "Alterada manualmente" in response.text
        assert "Desatualizada" in response.text
        assert "Desativada" in response.text
    finally:
        _limpar_planeamento_teste()


def test_plano_treino_mostra_origem_e_estado_da_sessao_global():
    from database import SessionLocal
    from models.planeamento import SessaoTreino

    client = _criar_client()
    _limpar_planeamento_teste()

    try:
        contexto = _criar_contexto_sincronizacao()
        _fazer_login(client, "admin")

        client.post(
            f"/planeamento-clube/semanal/{contexto['semanal_id']}/sincronizar",
            follow_redirects=False,
        )

        db = SessionLocal()
        try:
            sessao = db.query(SessaoTreino).filter(
                SessaoTreino.evento_planeamento_clube_id == contexto["evento_unico_id"],
                SessaoTreino.origem == "planeamento_global",
            ).first()
            assert sessao is not None
            sessao_id = sessao.id
        finally:
            db.close()

        response = client.get(f"/treino/sessoes/{sessao_id}", follow_redirects=False)

        assert response.status_code == 200
        assert "Planeamento Global do Clube" in response.text
        assert "Sincronizada" in response.text
        assert "Plano Semanal do Clube" in response.text
    finally:
        _limpar_planeamento_teste()


def test_evento_global_mostra_origem_no_contexto_da_equipa():
    client = _criar_client()
    _fazer_login(client, "coordenador")
    _limpar_planeamento_teste()

    try:
        equipa_id_1, _ = _criar_equipas_teste()
        client.post(
            "/planeamento-clube/eventos/novo",
            data={
                "tipo": "evento_clube",
                "titulo": TITULO_EVENTO_MANUAL,
                "descricao": "",
                "data_evento": "2025-09-05",
                "hora_inicio": "10:00",
                "hora_fim": "12:00",
                "planeamento_anual_id": "",
                "planeamento_mensal_id": "",
                "plano_semanal_id": "",
                "equipas_ids": [str(equipa_id_1)],
                "espaco_id": "",
                "treinador_id": "",
                "aplica_a_todas_equipas": "false",
                "observacoes": "",
            },
            follow_redirects=False,
        )

        detalhe_equipa = client.get(f"/equipas/{equipa_id_1}/eventos", follow_redirects=False)

        assert detalhe_equipa.status_code == 200
        assert TITULO_EVENTO_MANUAL in detalhe_equipa.text
        assert "Planeamento Global do Clube" in detalhe_equipa.text
    finally:
        _limpar_planeamento_teste()


def test_sincronizacao_inativa_sessao_quando_evento_e_removido():
    from database import SessionLocal
    from models.planeamento import SessaoTreino
    from models.planeamento_clube import EventoPlaneamentoClube

    client = _criar_client()
    _limpar_planeamento_teste()

    try:
        contexto = _criar_contexto_sincronizacao()
        _fazer_login(client, "coordenador")

        client.post(f"/planeamento-clube/semanal/{contexto['semanal_id']}/sincronizar", follow_redirects=False)

        response_eliminar = client.post(
            f"/planeamento-clube/eventos/{contexto['evento_unico_id']}/eliminar",
            follow_redirects=False,
        )
        assert response_eliminar.status_code == 303

        client.post(f"/planeamento-clube/semanal/{contexto['semanal_id']}/sincronizar", follow_redirects=False)

        db = SessionLocal()
        try:
            sessoes = db.query(SessaoTreino).filter(
                SessaoTreino.plano_semanal_clube_id == contexto["semanal_id"],
                SessaoTreino.origem == "planeamento_global",
                SessaoTreino.ativa == False,
            ).all()
            assert len(sessoes) == 1
            assert sessoes[0].ativa is False
            assert sessoes[0].sincronizada is False
        finally:
            db.close()
    finally:
        _limpar_planeamento_teste()


def test_sincronizacao_inativa_sessao_quando_evento_deixa_de_se_aplicar_a_equipa():
    from database import SessionLocal
    from models.planeamento import SessaoTreino
    from models.planeamento_clube import EventoPlaneamentoClube

    client = _criar_client()
    _limpar_planeamento_teste()

    try:
        contexto = _criar_contexto_sincronizacao()
        _fazer_login(client, "coordenador")

        client.post(f"/planeamento-clube/semanal/{contexto['semanal_id']}/sincronizar", follow_redirects=False)

        db = SessionLocal()
        try:
            evento = db.query(EventoPlaneamentoClube).filter(
                EventoPlaneamentoClube.id == contexto["evento_multi_id"]
            ).first()
            evento.equipas = [equipa for equipa in evento.equipas if equipa.id == contexto["equipa_1_id"]]
            evento.equipa_id = contexto["equipa_1_id"]
            db.commit()
        finally:
            db.close()

        client.post(f"/planeamento-clube/semanal/{contexto['semanal_id']}/sincronizar", follow_redirects=False)

        db = SessionLocal()
        try:
            sessoes = db.query(SessaoTreino).filter(
                SessaoTreino.evento_planeamento_clube_id == contexto["evento_multi_id"]
            ).all()
            assert len(sessoes) == 2

            estados_por_equipa = {}
            for sessao in sessoes:
                equipa_id = sessao.microciclo.mesociclo.macrociclo.equipa_id
                estados_por_equipa[equipa_id] = sessao.ativa

            assert estados_por_equipa[contexto["equipa_1_id"]] is True
            assert estados_por_equipa[contexto["equipa_2_id"]] is False
        finally:
            db.close()
    finally:
        _limpar_planeamento_teste()


def test_detalhe_anual_tem_link_e_calendario_anual_responde():
    client = _criar_client()
    _limpar_planeamento_teste()

    try:
        _fazer_login(client, "coordenador")
        anual_id, _, _ = _criar_estrutura_semanal_teste(client)

        client.post(
            "/planeamento-clube/eventos/novo",
            data={
                "tipo": "evento_clube",
                "titulo": TITULO_EVENTO_MANUAL,
                "descricao": "",
                "data_evento": "2025-09-05",
                "hora_inicio": "10:00",
                "hora_fim": "12:00",
                "planeamento_anual_id": str(anual_id),
                "planeamento_mensal_id": "",
                "plano_semanal_id": "",
                "equipa_id": "",
                "treinador_id": "",
                "observacoes": "",
            },
            follow_redirects=False,
        )

        detalhe = client.get(f"/planeamento-clube/anual/{anual_id}", follow_redirects=False)
        calendario = client.get(f"/planeamento-clube/anual/{anual_id}/calendario", follow_redirects=False)

        assert detalhe.status_code == 200
        assert "/calendario" in detalhe.text
        assert calendario.status_code == 200
        assert "Calendário Anual" in calendario.text
        assert TITULO_EVENTO_MANUAL in calendario.text
    finally:
        _limpar_planeamento_teste()


def test_detalhe_espaco_separa_atribuicoes_associadas_e_ocupacao_recente():
    from database import SessionLocal
    from models.atribuicao_espaco_semanal import (
        AtribuicaoEspacoSemanal,
        EstadoAtribuicaoEspacoEnum,
        OrigemAtribuicaoEspacoEnum,
        TipoOcupacaoEspacoEnum,
    )
    from models.espaco_treino import EspacoTreino, TipoEspacoTreinoEnum
    from models.planeamento_clube import PlaneamentoClubeAnual, PlaneamentoClubeMensal, PlanoSemanalClube

    client = _criar_client()
    _limpar_planeamento_teste()

    try:
        _fazer_login(client, "coordenador")

        db = SessionLocal()
        try:
            espaco = EspacoTreino(
                nome=NOME_ESPACO_TESTE,
                tipo=TipoEspacoTreinoEnum.pavilhao,
                localizacao="Complexo",
                capacidade=100,
                ativo=True,
                observacoes=None,
            )
            db.add(espaco)
            db.commit()
            db.refresh(espaco)

            anual = PlaneamentoClubeAnual(
                epoca="2025/2026",
                titulo=TITULO_ANUAL_TESTE,
                data_inicio=date.today(),
                data_fim=date.today(),
                objetivos_gerais=None,
                observacoes=None,
                ativo=True,
            )
            db.add(anual)
            db.commit()
            db.refresh(anual)

            mensal = PlaneamentoClubeMensal(
                planeamento_anual_id=anual.id,
                ano=date.today().year,
                mes=date.today().month,
                titulo=TITULO_MENSAL_TESTE,
                objetivos_mes=None,
                observacoes=None,
                estado="rascunho",
            )
            db.add(mensal)
            db.commit()
            db.refresh(mensal)

            semanal = PlanoSemanalClube(
                planeamento_mensal_id=mensal.id,
                titulo=TITULO_SEMANAL_TESTE,
                data_inicio=date.today(),
                data_fim=date.today(),
                observacoes=None,
                estado="rascunho",
            )
            db.add(semanal)
            db.commit()
            db.refresh(semanal)

            atribuicao_passada = AtribuicaoEspacoSemanal(
                plano_semanal_id=semanal.id,
                espaco_id=espaco.id,
                data=date.today() - timedelta(days=1),
                hora_inicio="18:00",
                hora_fim="19:00",
                tipo_ocupacao=TipoOcupacaoEspacoEnum.atividade,
                estado=EstadoAtribuicaoEspacoEnum.publicado,
                origem=OrigemAtribuicaoEspacoEnum.manual,
                observacoes=None,
            )
            atribuicao_futura = AtribuicaoEspacoSemanal(
                plano_semanal_id=semanal.id,
                espaco_id=espaco.id,
                data=date.today(),
                hora_inicio="20:00",
                hora_fim="21:00",
                tipo_ocupacao=TipoOcupacaoEspacoEnum.treino_equipa,
                estado=EstadoAtribuicaoEspacoEnum.publicado,
                origem=OrigemAtribuicaoEspacoEnum.manual,
                observacoes=None,
            )
            db.add_all([atribuicao_passada, atribuicao_futura])
            db.commit()
        finally:
            db.close()

        detalhe = client.get(f"/planeamento-clube/espacos/{espaco.id}", follow_redirects=False)

        assert detalhe.status_code == 200
        assert "Atribuições associadas" in detalhe.text
        assert "Ocupação recente" in detalhe.text
        assert "treino_equipa" in detalhe.text
        assert "atividade" in detalhe.text
    finally:
        _limpar_planeamento_teste()

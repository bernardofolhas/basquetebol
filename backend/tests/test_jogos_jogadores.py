from datetime import date
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from main import app
from models.jogo import Jogo
from routers.jogos import _mensagem_novo_jogo
from testsupport import TestClient


UTILIZADORES_TESTE = {
    "admin": {"username": "admin", "password": "admin123"},
    "coordenador": {"username": "coord", "password": "coord123"},
}

NOME_EQUIPA_TESTE = "Equipa Jogos Jogadores Sprint 12"
ADVERSARIO_JOGO_TESTE = "Adversario Jogos Jogadores Sprint 12"
NOME_JOGADOR_TESTE = "Jogador Integridade Sprint 12"


def _criar_client():
    return TestClient(app)


def test_mensagem_de_notificacao_de_jogo_inclui_contexto_operacional():
    jogo = Jogo(
        data=date(2026, 9, 5),
        hora="18:30",
        local="Pavilhão Principal",
        adversario="Clube Visitante",
        em_casa=False,
        equipa_id=1,
    )

    assert _mensagem_novo_jogo(jogo) == "Clube Visitante · fora · 05/09/2026 · 18:30 · Pavilhão Principal"


def _fazer_login(client: TestClient, perfil: str):
    response = client.post(
        "/login-form",
        data=UTILIZADORES_TESTE[perfil],
        follow_redirects=False,
    )
    assert response.status_code in [302, 303]
    assert response.headers["location"] == "/dashboard"


def _limpar_dados_teste():
    from database import SessionLocal
    from models.assiduidade import RegistoAssiduidade
    from models.equipa import Equipa
    from models.fisico import TesteFisico
    from models.jogador import Jogador, RegistoAntropometrico
    from models.jogo import Convocado, Jogo, PlanoJogo
    from models.planeamento import Macrociclo, Mesociclo, Microciclo, SessaoTreino

    db = SessionLocal()
    try:
        for registo in db.query(RegistoAssiduidade).all():
            if registo.jogador and registo.jogador.nome == NOME_JOGADOR_TESTE:
                db.delete(registo)

        for convocado in db.query(Convocado).all():
            if convocado.jogador and convocado.jogador.nome == NOME_JOGADOR_TESTE:
                db.delete(convocado)

        for teste in db.query(TesteFisico).all():
            if teste.jogador and teste.jogador.nome == NOME_JOGADOR_TESTE:
                db.delete(teste)

        for registo in db.query(RegistoAntropometrico).all():
            if registo.jogador and registo.jogador.nome == NOME_JOGADOR_TESTE:
                db.delete(registo)

        for plano in db.query(PlanoJogo).all():
            jogo = plano.jogo
            if jogo and jogo.adversario == ADVERSARIO_JOGO_TESTE:
                db.delete(plano)

        for sessao in db.query(SessaoTreino).all():
            try:
                equipa = sessao.microciclo.mesociclo.macrociclo.equipa
                if equipa and equipa.nome == NOME_EQUIPA_TESTE:
                    db.delete(sessao)
            except Exception:
                continue

        for micro in db.query(Microciclo).all():
            if micro.mesociclo and micro.mesociclo.macrociclo and micro.mesociclo.macrociclo.equipa and micro.mesociclo.macrociclo.equipa.nome == NOME_EQUIPA_TESTE:
                db.delete(micro)

        for meso in db.query(Mesociclo).all():
            if meso.macrociclo and meso.macrociclo.equipa and meso.macrociclo.equipa.nome == NOME_EQUIPA_TESTE:
                db.delete(meso)

        for macro in db.query(Macrociclo).all():
            if macro.equipa and macro.equipa.nome == NOME_EQUIPA_TESTE:
                db.delete(macro)

        for jogo in db.query(Jogo).filter(Jogo.adversario == ADVERSARIO_JOGO_TESTE).all():
            db.delete(jogo)

        for jogador in db.query(Jogador).filter(Jogador.nome == NOME_JOGADOR_TESTE).all():
            db.delete(jogador)

        for equipa in db.query(Equipa).filter(Equipa.nome == NOME_EQUIPA_TESTE).all():
            db.delete(equipa)

        db.commit()
    finally:
        db.close()


def _criar_equipa_e_jogo():
    from database import SessionLocal
    from models.equipa import Equipa, EscalaoEnum, GeneroEnum
    from models.jogo import Jogo

    db = SessionLocal()
    try:
        equipa = Equipa(
            nome=NOME_EQUIPA_TESTE,
            escalao=EscalaoEnum.senior,
            genero=GeneroEnum.masculino,
            seccionista=None,
        )
        db.add(equipa)
        db.commit()
        db.refresh(equipa)

        jogo = Jogo(
            data=date.fromisoformat("2026-04-20"),
            hora="15:00",
            local="Pavilhão Municipal",
            adversario=ADVERSARIO_JOGO_TESTE,
            competicao="Campeonato Nacional",
            em_casa=True,
            observacoes="Jogo de teste",
            equipa_id=equipa.id,
        )
        db.add(jogo)
        db.commit()
        db.refresh(jogo)
        return equipa.id, jogo.id
    finally:
        db.close()


def _criar_contexto_jogador_com_assiduidade():
    from database import SessionLocal
    from models.assiduidade import RegistoAssiduidade
    from models.equipa import Equipa, EscalaoEnum, GeneroEnum
    from models.fisico import TesteFisico
    from models.jogador import Jogador, RegistoAntropometrico
    from models.jogo import Convocado, Jogo, PlanoJogo
    from models.planeamento import Macrociclo, Mesociclo, Microciclo, SessaoTreino

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

        jogador = Jogador(nome=NOME_JOGADOR_TESTE, equipa_id=equipa.id)
        db.add(jogador)
        db.commit()
        db.refresh(jogador)

        macro = Macrociclo(numero=1, data_inicio=date.fromisoformat("2026-04-01"), data_fim=date.fromisoformat("2026-04-30"), equipa_id=equipa.id)
        db.add(macro)
        db.commit()
        db.refresh(macro)

        meso = Mesociclo(numero=1, data_inicio=date.fromisoformat("2026-04-01"), data_fim=date.fromisoformat("2026-04-30"), macrociclo_id=macro.id)
        db.add(meso)
        db.commit()
        db.refresh(meso)

        micro = Microciclo(numero=1, data_inicio=date.fromisoformat("2026-04-14"), data_fim=date.fromisoformat("2026-04-20"), tipo="competitivo", mesociclo_id=meso.id)
        db.add(micro)
        db.commit()
        db.refresh(micro)

        sessao = SessaoTreino(data=date.fromisoformat("2026-04-16"), local="Pavilhão", microciclo_id=micro.id, origem="manual", sincronizada=False, alterada_manual=False, ativa=True)
        db.add(sessao)
        db.commit()
        db.refresh(sessao)

        registo_assiduidade = RegistoAssiduidade(sessao_id=sessao.id, jogador_id=jogador.id, presente=True)
        registo_antropometrico = RegistoAntropometrico(jogador_id=jogador.id, data=date.fromisoformat("2026-04-10"), altura="180", peso="75")
        teste_fisico = TesteFisico(jogador_id=jogador.id, data=date.fromisoformat("2026-04-11"), tipo_teste="Yo-Yo", resultado=18.5, unidade="nível")
        db.add_all([registo_assiduidade, registo_antropometrico, teste_fisico])
        db.commit()

        jogo = Jogo(
            data=date.fromisoformat("2026-04-20"),
            hora="15:00",
            local="Pavilhão Municipal",
            adversario=ADVERSARIO_JOGO_TESTE,
            competicao="Campeonato Nacional",
            em_casa=True,
            equipa_id=equipa.id,
        )
        db.add(jogo)
        db.commit()
        db.refresh(jogo)

        convocado = Convocado(jogo_id=jogo.id, jogador_id=jogador.id)
        plano = PlanoJogo(jogo_id=jogo.id, titular_1=jogador.id)
        db.add_all([convocado, plano])
        db.commit()

        return jogador.id, jogo.id
    finally:
        db.close()


def test_detalhe_do_jogo_mostra_acoes_de_editar_e_eliminar():
    client = _criar_client()
    _limpar_dados_teste()

    try:
        _, jogo_id = _criar_equipa_e_jogo()
        _fazer_login(client, "admin")

        response = client.get(f"/jogos/{jogo_id}", follow_redirects=False)

        assert response.status_code == 200
        assert "Editar Jogo" in response.text
        assert "Eliminar Jogo" in response.text
    finally:
        _limpar_dados_teste()


def test_edicao_de_jogo_funciona():
    from database import SessionLocal
    from models.jogo import Jogo

    client = _criar_client()
    _limpar_dados_teste()

    try:
        _, jogo_id = _criar_equipa_e_jogo()
        _fazer_login(client, "coordenador")

        response = client.post(
            f"/jogos/{jogo_id}/editar",
            data={
                "data": "2026-04-21",
                "hora": "16:30",
                "local": "Pavilhão Editado",
                "adversario": ADVERSARIO_JOGO_TESTE,
                "competicao": "Taça",
                "em_casa": "false",
                "observacoes": "Observação editada",
            },
            follow_redirects=False,
        )

        assert response.status_code == 303

        db = SessionLocal()
        try:
            jogo = db.query(Jogo).filter(Jogo.id == jogo_id).first()
            assert str(jogo.data) == "2026-04-21"
            assert jogo.hora == "16:30"
            assert jogo.local == "Pavilhão Editado"
            assert jogo.competicao == "Taça"
            assert jogo.em_casa is False
        finally:
            db.close()
    finally:
        _limpar_dados_teste()


def test_eliminacao_de_jogo_funciona():
    from database import SessionLocal
    from models.jogo import Jogo

    client = _criar_client()
    _limpar_dados_teste()

    try:
        equipa_id, jogo_id = _criar_equipa_e_jogo()
        _fazer_login(client, "admin")

        response = client.post(f"/jogos/{jogo_id}/eliminar", follow_redirects=False)

        assert response.status_code == 303
        assert response.headers["location"] == f"/jogos/equipas/{equipa_id}"

        db = SessionLocal()
        try:
            jogo = db.query(Jogo).filter(Jogo.id == jogo_id).first()
            assert jogo is None
        finally:
            db.close()
    finally:
        _limpar_dados_teste()


def test_apagar_jogador_com_assiduidade_e_dependencias_nao_gera_integrity_error():
    from database import SessionLocal
    from models.assiduidade import RegistoAssiduidade
    from models.fisico import TesteFisico
    from models.jogador import Jogador, RegistoAntropometrico
    from models.jogo import Convocado, PlanoJogo

    client = _criar_client()
    _limpar_dados_teste()

    try:
        jogador_id, jogo_id = _criar_contexto_jogador_com_assiduidade()
        _fazer_login(client, "admin")

        response = client.post(f"/jogadores/{jogador_id}/apagar", follow_redirects=False)

        assert response.status_code == 303
        assert response.headers["location"] == "/jogadores"

        db = SessionLocal()
        try:
            assert db.query(Jogador).filter(Jogador.id == jogador_id).first() is None
            assert db.query(RegistoAssiduidade).filter(RegistoAssiduidade.jogador_id == jogador_id).first() is None
            assert db.query(RegistoAntropometrico).filter(RegistoAntropometrico.jogador_id == jogador_id).first() is None
            assert db.query(TesteFisico).filter(TesteFisico.jogador_id == jogador_id).first() is None
            assert db.query(Convocado).filter(Convocado.jogador_id == jogador_id).first() is None

            plano = db.query(PlanoJogo).filter(PlanoJogo.jogo_id == jogo_id).first()
            assert plano is not None
            assert plano.titular_1 is None
        finally:
            db.close()
    finally:
        _limpar_dados_teste()

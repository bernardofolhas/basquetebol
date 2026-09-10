from auth import verificar_password
from database import SessionLocal
from models.questionario import RespostaQuestionarioDiario
from models.utilizador import PerfilEnum, Utilizador
from test_fase2_assiduidade_evolucao import _criar_contexto, _limpar_contexto
from testsupport import TestClient


def test_conta_atleta_questionario_e_painel_tecnico(client_admin):
    db, equipa_id, jogador_id, outro_id, macro_id = _criar_contexto()
    conta_id = None
    try:
        painel = client_admin.get(f"/questionarios/equipas/{equipa_id}")
        assert painel.status_code == 200
        assert "Questionário diário" in painel.text
        assert "responderam hoje" in painel.text

        conta = db.query(Utilizador).execution_options(ignorar_clube=True).filter_by(
            jogador_id=jogador_id
        ).one()
        conta_id = conta.id
        assert conta.perfil == PerfilEnum.atleta
        assert conta.username.startswith("jogadorafase")
        assert conta.deve_alterar_password is True
        assert verificar_password(f"{conta.username}1234", conta.password_hash)

        cliente_atleta = TestClient(client_admin.app)
        login = cliente_atleta.post(
            "/login-form",
            data={"username": conta.username, "password": f"{conta.username}1234"},
            follow_redirects=False,
        )
        assert login.status_code == 303
        assert login.headers["location"] == "/questionarios/diario"
        primeiro_acesso = cliente_atleta.get("/questionarios/diario", follow_redirects=False)
        assert primeiro_acesso.status_code == 303
        assert primeiro_acesso.headers["location"] == "/minha-conta"

        conta.deve_alterar_password = False
        db.commit()
        area_interna = cliente_atleta.get("/jogadores", follow_redirects=False)
        assert area_interna.status_code == 303
        assert area_interna.headers["location"] == "/questionarios/diario"
        questionario = cliente_atleta.get("/questionarios/diario")
        assert questionario.status_code == 200
        assert "Perceção subjetiva de esforço" in questionario.text
        resposta = cliente_atleta.post(
            "/questionarios/diario",
            data={
                "tipo_sessao": "treino",
                "horas_sono": "7.5",
                "qualidade_sono": "2",
                "pse_esforco": "8",
                "dor_membros_inferiores": "7",
                "dor_membros_superiores": "3",
                "tem_queixa": "sim",
                "descricao_queixa": "Dor no joelho direito",
                "observacoes": "Carga elevada",
            },
            follow_redirects=False,
        )
        assert resposta.status_code == 303
        assert resposta.headers["location"].startswith("/questionarios/diario?resposta_id=")
        db.expire_all()
        registo = db.query(RespostaQuestionarioDiario).filter_by(jogador_id=jogador_id).one()
        assert (registo.pse_esforco, registo.qualidade_sono, registo.tem_queixa) == (8, 2, True)

        nova_resposta = cliente_atleta.post(
            "/questionarios/diario",
            data={
                "tipo_sessao": "treino",
                "horas_sono": "8",
                "qualidade_sono": "4",
                "pse_esforco": "4",
                "dor_membros_inferiores": "2",
                "dor_membros_superiores": "1",
                "tem_queixa": "nao",
                "descricao_queixa": "",
                "observacoes": "Depois da recuperação",
            },
            follow_redirects=False,
        )
        assert nova_resposta.status_code == 303
        db.expire_all()
        assert db.query(RespostaQuestionarioDiario).filter_by(jogador_id=jogador_id).count() == 2

        editar_resposta = cliente_atleta.post(
            "/questionarios/diario",
            data={
                "resposta_id": str(registo.id),
                "tipo_sessao": "treino",
                "horas_sono": "7.5",
                "qualidade_sono": "2",
                "pse_esforco": "9",
                "dor_membros_inferiores": "7",
                "dor_membros_superiores": "3",
                "tem_queixa": "sim",
                "descricao_queixa": "Dor no joelho direito",
                "observacoes": "Resposta corrigida",
            },
            follow_redirects=False,
        )
        assert editar_resposta.status_code == 303
        db.expire_all()
        assert db.query(RespostaQuestionarioDiario).filter_by(id=registo.id).one().pse_esforco == 9
        assert db.query(RespostaQuestionarioDiario).filter_by(jogador_id=jogador_id).count() == 2

        painel = client_admin.get(f"/questionarios/equipas/{equipa_id}")
        assert "Dor no joelho direito" in painel.text
        assert "Atenção necessária" in painel.text
        assert "2 registos" in painel.text
        assert "Registos recebidos hoje" in painel.text
        assert "9/10" in painel.text
        assert "4/10" in painel.text
        historico = cliente_atleta.get("/questionarios/historico")
        assert historico.status_code == 200
        assert "9/10" in historico.text
        assert "Editar" in historico.text
    finally:
        db.query(RespostaQuestionarioDiario).filter(
            RespostaQuestionarioDiario.jogador_id.in_([jogador_id, outro_id])
        ).delete(synchronize_session=False)
        db.query(Utilizador).execution_options(ignorar_clube=True).filter(
            Utilizador.jogador_id.in_([jogador_id, outro_id])
        ).delete(synchronize_session=False)
        db.commit()
        _limpar_contexto(db, equipa_id, jogador_id, outro_id, macro_id)
        db.close()

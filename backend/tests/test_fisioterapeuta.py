from datetime import date, datetime, timedelta
from uuid import uuid4

from database import SessionLocal
from models.equipa import Equipa
from models.questionario import (
    AplicacaoQuestionario,
    PerguntaQuestionario,
    QuestionarioPersonalizado,
    RespostaPerguntaQuestionario,
    SubmissaoQuestionario,
)
from models.utilizador import PerfilEnum, Utilizador
from services.dashboard_service import obter_resumo_fisioterapia
from test_fase2_assiduidade_evolucao import _criar_contexto, _limpar_contexto


def test_criacao_fisioterapeuta_exige_equipa(client_admin):
    sufixo = uuid4().hex[:8]
    formulario = client_admin.get("/admin/utilizadores/novo")
    assert formulario.status_code == 200
    assert 'value="fisioterapeuta"' in formulario.text
    assert "Acesso de fisioterapeuta" in formulario.text

    resposta = client_admin.post(
        "/admin/utilizadores/novo",
        data={
            "nome": "Fisioterapeuta sem equipa",
            "username": f"fisio_sem_{sufixo}",
            "email": f"fisio-sem-{sufixo}@example.test",
            "password": "FisioTeste123!",
            "perfil": "fisioterapeuta",
        },
        follow_redirects=False,
    )

    assert resposta.status_code == 200
    assert "Seleciona pelo menos uma equipa" in resposta.text


def test_fisioterapeuta_tem_primeiro_acesso_e_dashboard_proprio(client_admin):
    db = SessionLocal()
    conta_id = None
    try:
        equipa = db.query(Equipa).order_by(Equipa.id).first()
        assert equipa is not None
        sufixo = uuid4().hex[:8]
        username = f"fisio_{sufixo}"
        password = "FisioTeste123!"
        resposta = client_admin.post(
            "/admin/utilizadores/novo",
            data={
                "nome": "Fisioterapeuta de teste",
                "username": username,
                "email": f"{username}@example.test",
                "password": password,
                "perfil": "fisioterapeuta",
                "equipa_ids": str(equipa.id),
            },
            follow_redirects=False,
        )
        assert resposta.status_code == 303

        conta = db.query(Utilizador).filter(Utilizador.username == username).one()
        conta_id = conta.id
        assert conta.perfil == PerfilEnum.fisioterapeuta
        assert conta.deve_alterar_password is True
        assert [item.id for item in conta.equipas_staff] == [equipa.id]

        login = client_admin.post(
            "/login-form",
            data={"username": username, "password": password},
            follow_redirects=False,
        )
        assert login.status_code == 303
        assert login.headers["location"] == "/dashboard"
        primeiro_acesso = client_admin.get("/dashboard", follow_redirects=False)
        assert primeiro_acesso.status_code == 303
        assert primeiro_acesso.headers["location"] == "/minha-conta"

        conta.deve_alterar_password = False
        db.commit()
        dashboard = client_admin.get("/dashboard")
        assert dashboard.status_code == 200
        assert "Dashboard do fisioterapeuta" in dashboard.text
        assert equipa.nome in dashboard.text
        assert "Questionários" in dashboard.text
        jogadores = client_admin.get("/jogadores")
        assert jogadores.status_code == 200
        assert "Eliminar selecionados" in jogadores.text
        assert f"/jogadores/{equipa.jogadores[0].id}/apagar" in jogadores.text
        plantel = client_admin.get(f"/equipas/{equipa.id}/plantel")
        assert plantel.status_code == 200
        assert "Eliminar selecionados" in plantel.text
        ficha = client_admin.get(f"/jogadores/{equipa.jogadores[0].id}")
        assert ficha.status_code == 200
        assert f"/jogadores/{equipa.jogadores[0].id}/apagar" in ficha.text
        dashboard_filtrado = client_admin.get(
            "/dashboard?dias=14&metrica=respondentes"
        )
        assert dashboard_filtrado.status_code == 200
        assert "Atletas que responderam" in dashboard_filtrado.text
    finally:
        if conta_id:
            conta = db.query(Utilizador).filter(Utilizador.id == conta_id).first()
            if conta:
                conta.equipas_staff = []
                db.delete(conta)
                db.commit()
        db.close()


def test_dashboard_conta_submissao_pela_data_real_de_envio():
    db, equipa_id, jogador_id, outro_id, macro_id = _criar_contexto()
    try:
        equipa = db.query(Equipa).filter_by(id=equipa_id).one()
        questionario = QuestionarioPersonalizado(
            clube_id=equipa.clube_id,
            equipa_id=equipa_id,
            nome="PSE de teste",
            ativo=True,
        )
        pergunta = PerguntaQuestionario(
            texto="Perceção subjetiva de esforço (PSE)",
            tipo="escala",
            minimo=1,
            maximo=10,
            obrigatoria=True,
            questionario=questionario,
        )
        aplicacao = AplicacaoQuestionario(
            clube_id=equipa.clube_id,
            equipa_id=equipa_id,
            questionario=questionario,
            data=date.today() - timedelta(days=1),
            ativa=True,
        )
        submissao = SubmissaoQuestionario(
            clube_id=equipa.clube_id,
            aplicacao=aplicacao,
            jogador_id=jogador_id,
            criado_em=datetime.now(),
        )
        db.add_all([questionario, pergunta, aplicacao, submissao])
        db.flush()
        db.add(RespostaPerguntaQuestionario(
            submissao_id=submissao.id,
            pergunta_id=pergunta.id,
            valor="8",
        ))
        db.commit()

        resumo = obter_resumo_fisioterapia(db, equipa, hoje=date.today(), dias=7)

        assert resumo["respostas_hoje"] == 1
        assert resumo["media_rpe_atletas"] == 8.0
        assert resumo["indicador_selecionado"]["valor"] == "rpe"
    finally:
        questionario = locals().get("questionario")
        if questionario is not None:
            db.delete(questionario)
            db.flush()
        _limpar_contexto(db, equipa_id, jogador_id, outro_id, macro_id)
        db.close()

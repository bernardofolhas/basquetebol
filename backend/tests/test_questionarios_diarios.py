from datetime import date, timedelta
import json

from auth import verificar_password
from database import SessionLocal
from models.jogo import Jogo
from models.planeamento import Macrociclo, Mesociclo, Microciclo, SessaoTreino
from models.questionario import (
    AplicacaoQuestionario,
    QuestionarioPersonalizado,
    RespostaQuestionarioDiario,
    SubmissaoQuestionario,
)
from models.utilizador import PerfilEnum, Utilizador
from test_fase2_assiduidade_evolucao import _criar_contexto, _limpar_contexto
from testsupport import TestClient


def test_conta_atleta_questionario_e_painel_tecnico(client_admin):
    db, equipa_id, jogador_id, outro_id, macro_id = _criar_contexto()
    conta_id = None
    try:
        selecao = client_admin.get(f"/questionarios/equipas/{equipa_id}")
        assert selecao.status_code == 200
        assert "Escolher questionário" in selecao.text
        assert "Ainda não existem questionários" in selecao.text
        assert f"/questionarios/equipas/{equipa_id}/matinal" not in selecao.text
        painel_matinal = client_admin.get(f"/questionarios/equipas/{equipa_id}/matinal")
        assert painel_matinal.status_code == 200
        assert "responderam hoje" in painel_matinal.text

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
        assert resposta.headers["location"] == "/questionarios/diario"
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
        assert nova_resposta.headers["location"] == "/questionarios/diario"
        db.expire_all()
        assert db.query(RespostaQuestionarioDiario).filter_by(jogador_id=jogador_id).count() == 1
        assert db.query(RespostaQuestionarioDiario).filter_by(id=registo.id).one().pse_esforco == 8

        fechado = cliente_atleta.get("/questionarios/diario")
        assert fechado.status_code == 200
        assert "Questionário concluído" in fechado.text
        assert "Editar resposta" not in fechado.text
        assert "Nova resposta" not in fechado.text

        painel = client_admin.get(f"/questionarios/equipas/{equipa_id}/matinal")
        assert "Questionário Matinal" in painel.text
        assert "Editar questionário" in painel.text
        assert "Análise" in painel.text
        assert "Respostas por atleta" in painel.text
        assert "Dor no joelho direito" in painel.text
        assert "Atenção necessária" in painel.text
        assert "Registos recebidos hoje" in painel.text
        assert "8/10" in painel.text
        selecao = client_admin.get(f"/questionarios/equipas/{equipa_id}")
        assert "Questionário Matinal" in selecao.text
        assert "Modelo base" not in selecao.text
        historico = cliente_atleta.get("/questionarios/historico")
        assert historico.status_code == 200
        assert "8/10" in historico.text
        assert "Editar" not in historico.text
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


def test_cria_questionario_aplica_a_treino_e_recolhe_resultados(client_admin):
    db, equipa_id, jogador_id, outro_id, macro_id = _criar_contexto()
    try:
        construtor = client_admin.get(f"/questionarios/equipas/{equipa_id}/novo?modelo=pse-pos-treino")
        assert construtor.status_code == 200
        assert "Perceção subjetiva de esforço - Pós-treino" in construtor.text
        assert "Criar questionário" in construtor.text
        modelo_original = client_admin.get(
            f"/questionarios/equipas/{equipa_id}/novo?modelo=acompanhamento-diario-original"
        )
        assert modelo_original.status_code == 200
        assert "Questionário Matinal" in modelo_original.text
        assert "acompanhamento-diario-original" in modelo_original.text

        perguntas = [
            {
                "texto": "PSE da sessão",
                "tipo": "escala",
                "minimo": 1,
                "maximo": 10,
                "rotulo_minimo": "Leve",
                "rotulo_maximo": "Máximo",
                "obrigatoria": True,
            },
            {
                "texto": "Como terminou a sessão?",
                "tipo": "escolha",
                "opcoes": ["Bem", "Com limitações"],
                "obrigatoria": True,
            },
        ]
        criada = client_admin.post(
            f"/questionarios/equipas/{equipa_id}/criar",
            data={
                "nome": "PSE personalizado",
                "descricao": "Avaliação após a sessão",
                "perguntas_json": json.dumps(perguntas),
                "data_aplicacao": date.today().isoformat(),
            },
            follow_redirects=False,
        )
        assert criada.status_code == 303
        questionario = db.query(QuestionarioPersonalizado).filter_by(equipa_id=equipa_id).one()
        questionario_id = questionario.id
        aplicacao = db.query(AplicacaoQuestionario).filter_by(questionario_id=questionario.id).one()
        aplicacao_id = aplicacao.id
        assert len(questionario.perguntas) == 2
        assert aplicacao.data == date.today()
        selecao = client_admin.get(f"/questionarios/equipas/{equipa_id}")
        assert selecao.status_code == 200
        assert "Questionário Matinal" not in selecao.text
        assert "PSE personalizado" in selecao.text
        assert selecao.text.count("Abrir dashboard") == 1
        biblioteca = client_admin.get(f"/questionarios/equipas/{equipa_id}/biblioteca")
        assert biblioteca.status_code == 200
        assert "Dashboards por questionário" in biblioteca.text
        assert "Abrir dashboard" in biblioteca.text

        sessao = db.query(SessaoTreino).join(Microciclo).join(Mesociclo).join(Macrociclo).filter(
            Macrociclo.id == macro_id
        ).one()
        associada = client_admin.post(
            f"/questionarios/modelos/{questionario.id}/aplicar",
            data={"data_aplicacao": "", "sessao_treino_id": str(sessao.id)},
            follow_redirects=False,
        )
        assert associada.status_code == 303
        assert db.query(AplicacaoQuestionario).filter_by(
            questionario_id=questionario.id,
            sessao_treino_id=sessao.id,
        ).one().data == sessao.data

        client_admin.get(f"/questionarios/equipas/{equipa_id}/matinal")
        conta = db.query(Utilizador).execution_options(ignorar_clube=True).filter_by(jogador_id=jogador_id).one()
        conta.deve_alterar_password = False
        db.commit()
        cliente_atleta = TestClient(client_admin.app)
        cliente_atleta.post(
            "/login-form",
            data={"username": conta.username, "password": f"{conta.username}1234"},
            follow_redirects=False,
        )
        disponiveis = cliente_atleta.get("/questionarios/disponiveis")
        assert disponiveis.status_code == 200
        assert "PSE personalizado" in disponiveis.text
        formulario = cliente_atleta.get(f"/questionarios/responder/{aplicacao.id}")
        assert formulario.status_code == 200
        assert "PSE da sessão" in formulario.text
        ids = [pergunta.id for pergunta in questionario.perguntas]
        envio = cliente_atleta.post(
            f"/questionarios/responder/{aplicacao.id}",
            data={f"pergunta_{ids[0]}": "8", f"pergunta_{ids[1]}": "Bem"},
            follow_redirects=False,
        )
        assert envio.status_code == 303
        fechado = cliente_atleta.get(f"/questionarios/responder/{aplicacao.id}", follow_redirects=False)
        assert fechado.status_code == 303
        assert fechado.headers["location"] == "/questionarios/disponiveis"
        repetida = cliente_atleta.post(
            f"/questionarios/responder/{aplicacao.id}",
            data={f"pergunta_{ids[0]}": "3", f"pergunta_{ids[1]}": "Com limitações"},
            follow_redirects=False,
        )
        assert repetida.status_code == 303
        db.expire_all()
        assert db.query(SubmissaoQuestionario).filter_by(
            aplicacao_id=aplicacao.id,
            jogador_id=jogador_id,
        ).count() == 1
        disponiveis = cliente_atleta.get("/questionarios/disponiveis")
        assert "Concluído" in disponiveis.text
        assert "Resposta fechada" in disponiveis.text
        assert "Editar resposta" not in disponiveis.text

        resultados = client_admin.get(f"/questionarios/aplicacoes/{aplicacao.id}/resultados")
        assert resultados.status_code == 200
        assert "8.0" in resultados.text
        assert "Bem" in resultados.text
        assert "1/2" in resultados.text

        dashboard = client_admin.get(f"/questionarios/modelos/{questionario.id}")
        assert dashboard.status_code == 200
        assert "Dashboard do questionário" in dashboard.text
        assert "Editar questionário" in dashboard.text
        assert "Taxa de resposta" in dashboard.text
        assert "Estado dos atletas" in dashboard.text
        assert "Indicadores globais" in dashboard.text
        assert "Análise" in dashboard.text
        assert "Respostas por atleta" in dashboard.text
        assert "Resposta a resposta" in dashboard.text
        assert "Aplicações" in dashboard.text
        assert "Configuração" in dashboard.text
        assert "Retirar questionário e manter os dados" in dashboard.text
        assert "Eliminar questionário e todos os dados" in dashboard.text
        edicao = client_admin.get(f"/questionarios/modelos/{questionario.id}/editar")
        assert edicao.status_code == 200
        assert "PSE personalizado" in edicao.text
        assert "As respostas existentes serão mantidas" in edicao.text
        assert "Sempre que há um treino nesse dia" in edicao.text
        assert "Sempre que há um jogo nesse dia" in edicao.text
        assert "Sempre que há um treino físico nesse dia" in edicao.text
        assert "Aplicar diariamente" in edicao.text
        perguntas_editadas = [
            {**perguntas[0], "id": ids[0], "texto": "PSE final da sessão"},
            {**perguntas[1], "id": ids[1]},
        ]
        atualizada = client_admin.post(
            f"/questionarios/modelos/{questionario.id}/editar",
            data={
                "nome": "PSE personalizado atualizado",
                "descricao": "Nova versão do acompanhamento",
                "perguntas_json": json.dumps(perguntas_editadas),
            },
            follow_redirects=False,
        )
        assert atualizada.status_code == 303
        db.expire_all()
        versoes = db.query(QuestionarioPersonalizado).filter_by(equipa_id=equipa_id).all()
        assert len(versoes) == 1
        atualizado = versoes[0]
        assert atualizado.id == questionario.id
        assert atualizado.ativo is True
        assert atualizado.nome == "PSE personalizado atualizado"
        assert atualizada.headers["location"] == f"/questionarios/modelos/{questionario.id}"
        resultados_preservados = client_admin.get(f"/questionarios/aplicacoes/{aplicacao.id}/resultados")
        assert resultados_preservados.status_code == 200
        assert "8.0" in resultados_preservados.text
        assert "PSE final da sessão" in resultados_preservados.text

        arquivada = client_admin.post(
            f"/questionarios/modelos/{questionario.id}/eliminar",
            data={"modo": "arquivar"},
            follow_redirects=False,
        )
        assert arquivada.status_code == 303
        db.expire_all()
        assert db.query(QuestionarioPersonalizado).filter_by(id=questionario.id).one().ativo is False
        assert db.query(SubmissaoQuestionario).filter_by(aplicacao_id=aplicacao.id).count() == 1

        eliminada = client_admin.post(
            f"/questionarios/modelos/{questionario.id}/eliminar",
            data={"modo": "tudo"},
            follow_redirects=False,
        )
        assert eliminada.status_code == 303
        db.expire_all()
        assert db.query(QuestionarioPersonalizado).filter_by(id=questionario_id).first() is None
        assert db.query(SubmissaoQuestionario).filter_by(aplicacao_id=aplicacao_id).count() == 0
    finally:
        db.query(QuestionarioPersonalizado).filter(
            QuestionarioPersonalizado.equipa_id == equipa_id
        ).delete(synchronize_session=False)
        db.query(Utilizador).execution_options(ignorar_clube=True).filter(
            Utilizador.jogador_id.in_([jogador_id, outro_id])
        ).delete(synchronize_session=False)
        db.commit()
        _limpar_contexto(db, equipa_id, jogador_id, outro_id, macro_id)
        db.close()


def test_regras_automaticas_seguem_calendario_sem_duplicar(client_admin):
    db, equipa_id, jogador_id, outro_id, macro_id = _criar_contexto()
    jogo_id = None
    try:
        sessao_normal = db.query(SessaoTreino).join(Microciclo).join(Mesociclo).join(Macrociclo).filter(
            Macrociclo.id == macro_id
        ).one()
        data_normal = date.today() + timedelta(days=1)
        data_fisico = date.today() + timedelta(days=2)
        data_jogo = date.today() + timedelta(days=3)
        sessao_normal.data = data_normal
        sessao_normal.tipo_treino = "normal"
        sessao_normal.e_jogo = False
        sessao_fisico = SessaoTreino(
            clube_id=sessao_normal.clube_id,
            data=data_fisico,
            local="Ginásio",
            hora_inicio="10:00",
            hora_fim="11:00",
            tipo_treino="fisico",
            e_jogo=False,
            ativa=True,
            microciclo_id=sessao_normal.microciclo_id,
        )
        jogo = Jogo(
            clube_id=sessao_normal.clube_id,
            equipa_id=equipa_id,
            data=data_jogo,
            adversario="Adversário automático",
            em_casa=True,
        )
        db.add_all([sessao_fisico, jogo])
        db.commit()
        jogo_id = jogo.id

        perguntas = [{
            "texto": "Como estás?",
            "tipo": "escala",
            "minimo": 1,
            "maximo": 10,
            "obrigatoria": True,
        }]
        regras = {
            "diario": date.today(),
            "treino": data_normal,
            "treino_fisico": data_fisico,
            "jogo": data_jogo,
        }
        questionarios = {}
        for regra, data_esperada in regras.items():
            resposta = client_admin.post(
                f"/questionarios/equipas/{equipa_id}/criar",
                data={
                    "nome": f"Questionário {regra}",
                    "descricao": "Aplicação automática",
                    "perguntas_json": json.dumps(perguntas),
                    "data_aplicacao": "",
                    "regra_aplicacao": regra,
                },
                follow_redirects=False,
            )
            assert resposta.status_code == 303
            questionario = db.query(QuestionarioPersonalizado).filter_by(
                equipa_id=equipa_id,
                regra_aplicacao=regra,
            ).one()
            questionarios[regra] = questionario
            aplicacoes = db.query(AplicacaoQuestionario).filter_by(
                questionario_id=questionario.id,
                automatica=True,
            ).all()
            assert [item.data for item in aplicacoes] == [data_esperada]

        client_admin.get(f"/questionarios/equipas/{equipa_id}")
        client_admin.get(f"/questionarios/equipas/{equipa_id}")
        for questionario in questionarios.values():
            assert db.query(AplicacaoQuestionario).filter_by(
                questionario_id=questionario.id,
                automatica=True,
            ).count() == 1

        treino = questionarios["treino"]
        resposta = client_admin.post(
            f"/questionarios/modelos/{treino.id}/editar",
            data={
                "nome": treino.nome,
                "descricao": treino.descricao or "",
                "perguntas_json": json.dumps(perguntas),
                "regra_aplicacao": "manual",
            },
            follow_redirects=False,
        )
        assert resposta.status_code == 303
        db.expire_all()
        assert db.query(QuestionarioPersonalizado).filter_by(id=treino.id).one().regra_aplicacao == "manual"
        assert db.query(AplicacaoQuestionario).filter_by(
            questionario_id=treino.id,
            automatica=True,
        ).count() == 0
    finally:
        db.query(QuestionarioPersonalizado).filter(
            QuestionarioPersonalizado.equipa_id == equipa_id
        ).delete(synchronize_session=False)
        if jogo_id:
            db.query(Jogo).filter(Jogo.id == jogo_id).delete(synchronize_session=False)
        db.query(Utilizador).execution_options(ignorar_clube=True).filter(
            Utilizador.jogador_id.in_([jogador_id, outro_id])
        ).delete(synchronize_session=False)
        db.commit()
        _limpar_contexto(db, equipa_id, jogador_id, outro_id, macro_id)
        db.close()

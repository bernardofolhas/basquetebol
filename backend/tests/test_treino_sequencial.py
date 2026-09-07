from models.planeamento import Macrociclo, Mesociclo, Microciclo, SessaoTreino
from models.treino import PlanoTreino, ExercicioPlano
from test_fase2_assiduidade_evolucao import _criar_contexto, _limpar_contexto


def test_exercicios_sem_blocos_persistem_e_podem_ser_editados(client_admin):
    db, equipa_id, jogador_id, outro_id, macro_id = _criar_contexto()
    try:
        sessao = db.query(SessaoTreino).join(Microciclo).join(Mesociclo).join(Macrociclo).filter(
            Macrociclo.id == macro_id
        ).one()
        assert client_admin.get(f"/treino/sessoes/{sessao.id}").status_code == 200
        plano = db.query(PlanoTreino).filter_by(sessao_id=sessao.id).one()
        for nome in ("Passe em pares", "Finalizacao"):
            resposta = client_admin.post(
                f"/treino/planos/{plano.id}/exercicios",
                data={"nome": nome, "minutos": "15", "organizacao": "Dois grupos"},
                follow_redirects=False,
            )
            assert resposta.status_code == 303
        db.expire_all()
        exercicios = db.query(ExercicioPlano).filter_by(plano_id=plano.id).order_by(ExercicioPlano.ordem).all()
        assert [ex.nome for ex in exercicios] == ["Passe em pares", "Finalizacao"]
        assert not plano.blocos
        assert all(ex.bloco_id is None for ex in exercicios)
        resposta = client_admin.post(
            f"/treino/exercicios/{exercicios[0].id}/atualizar",
            data={"nome": "Passe em movimento", "minutos": "20"},
            follow_redirects=False,
        )
        assert resposta.status_code == 303
        pagina = client_admin.get(f"/treino/sessoes/{sessao.id}")
        assert pagina.status_code == 200
        assert "Passe em movimento" in pagina.text
        assert "Finalizacao" in pagina.text
    finally:
        _limpar_contexto(db, equipa_id, jogador_id, outro_id, macro_id)
        db.close()


def test_hora_do_novo_exercicio_continua_a_sequencia_do_plano(client_admin):
    db, equipa_id, jogador_id, outro_id, macro_id = _criar_contexto()
    try:
        sessao = db.query(SessaoTreino).join(Microciclo).join(Mesociclo).join(Macrociclo).filter(
            Macrociclo.id == macro_id
        ).one()
        pagina = client_admin.get(f"/treino/sessoes/{sessao.id}")
        assert 'name="hora" value="18:00"' in pagina.text

        plano = db.query(PlanoTreino).filter_by(sessao_id=sessao.id).one()
        client_admin.post(
            f"/treino/planos/{plano.id}/exercicios",
            data={"nome": "Primeiro", "minutos": "15"},
            follow_redirects=False,
        )
        pagina = client_admin.get(f"/treino/sessoes/{sessao.id}")
        assert 'name="hora" value="18:15"' in pagina.text

        client_admin.post(
            f"/treino/planos/{plano.id}/exercicios",
            data={"nome": "Segundo", "minutos": "20"},
            follow_redirects=False,
        )
        exercicios = db.query(ExercicioPlano).filter_by(plano_id=plano.id).order_by(ExercicioPlano.id).all()
        assert [(ex.hora, ex.minutos) for ex in exercicios] == [("18:00", 15), ("18:15", 20)]
    finally:
        _limpar_contexto(db, equipa_id, jogador_id, outro_id, macro_id)
        db.close()


def test_cartao_do_exercicio_mostra_dados_da_ficha(client_admin):
    db, equipa_id, jogador_id, outro_id, macro_id = _criar_contexto()
    try:
        sessao = db.query(SessaoTreino).join(Microciclo).join(Mesociclo).join(Macrociclo).filter(
            Macrociclo.id == macro_id
        ).one()
        client_admin.get(f"/treino/sessoes/{sessao.id}")
        plano = db.query(PlanoTreino).filter_by(sessao_id=sessao.id).one()
        resposta = client_admin.post(
            f"/treino/planos/{plano.id}/exercicios",
            data={
                "nome": "Finalização em vantagem",
                "categoria": "TIO",
                "hora": "18:15",
                "minutos": "20",
                "rpe": "7",
                "organizacao": "Três filas na linha final.",
                "coaching_points": "Atacar o cesto sem hesitar.",
            },
            follow_redirects=False,
        )
        assert resposta.status_code == 303
        pagina = client_admin.get(f"/treino/sessoes/{sessao.id}")
        assert pagina.status_code == 200
        for texto in (
            "Finalização em vantagem", "Hora", "18:15", "Duração", "20 min",
            "Tipo", "TIO", "RPE", "Organização", "Três filas na linha final.",
            "Coaching points", "Atacar o cesto sem hesitar.", "Acrescentar campo tático",
        ):
            assert texto in pagina.text
        assert 'class="training-exercise-card"' in pagina.text
        assert 'data-drawing-preview=' in pagina.text
        assert 'data-drawing-editor' in pagina.text
        assert 'action="/treino/exercicios/' in pagina.text
        assert "/notas" in pagina.text
        assert "Editar dados do exercício" not in pagina.text

        exercicio = db.query(ExercicioPlano).filter_by(plano_id=plano.id).one()
        notas = client_admin.post(
            f"/treino/exercicios/{exercicio.id}/notas",
            data={"organizacao": "Quatro grupos.", "coaching_points": "Passe forte."},
        )
        assert notas.status_code == 200
        assert notas.json() == {
            "sucesso": True,
            "organizacao": "Quatro grupos.",
            "coaching_points": "Passe forte.",
        }
        db.refresh(exercicio)
        assert exercicio.organizacao == "Quatro grupos."
        assert exercicio.coaching_points == "Passe forte."
    finally:
        _limpar_contexto(db, equipa_id, jogador_id, outro_id, macro_id)
        db.close()


def test_pdf_sem_modulo_de_blocos_nao_mostra_blocos_tecnicos(client_admin):
    db, equipa_id, jogador_id, outro_id, macro_id = _criar_contexto()
    try:
        sessao = db.query(SessaoTreino).join(Microciclo).join(Mesociclo).join(Macrociclo).filter(
            Macrociclo.id == macro_id
        ).one()
        client_admin.get(f"/treino/sessoes/{sessao.id}")
        plano = db.query(PlanoTreino).filter_by(sessao_id=sessao.id).one()
        client_admin.post(
            f"/treino/planos/{plano.id}/exercicios",
            data={"nome": "Aquecimento", "minutos": "10"},
            follow_redirects=False,
        )
        pagina = client_admin.get(f"/treino/sessoes/{sessao.id}/print")
        assert pagina.status_code == 200
        assert "Aquecimento" in pagina.text
        assert '<div class="block-summary">' not in pagina.text
        assert '<div class="block-title">' not in pagina.text
        assert "Bloco A" not in pagina.text
    finally:
        _limpar_contexto(db, equipa_id, jogador_id, outro_id, macro_id)
        db.close()

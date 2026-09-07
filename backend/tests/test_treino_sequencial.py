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

from datetime import date

from database import SessionLocal
from models.avaliacao import AvaliacaoJogador, ParametroAvaliacao
from models.equipa import Equipa, EscalaoEnum, GeneroEnum
from models.jogador import Jogador
from models.planeamento import Macrociclo, Mesociclo, Microciclo, SessaoTreino
from models.utilizador import Utilizador


def _criar_contexto():
    db = SessionLocal()
    clube_id = db.query(Utilizador.clube_id).filter(Utilizador.username == "admin").scalar()
    assert clube_id is not None
    equipa = Equipa(
        clube_id=clube_id,
        nome="Equipa Teste Análise",
        escalao=EscalaoEnum.sub18,
        genero=GeneroEnum.feminino,
    )
    jogadora_1 = Jogador(clube_id=clube_id, equipa=equipa, nome="Ana Avaliação", numero_camisola=4)
    jogadora_2 = Jogador(clube_id=clube_id, equipa=equipa, nome="Beatriz Avaliação", numero_camisola=8)
    macro = Macrociclo(
        clube_id=clube_id,
        equipa=equipa,
        numero=1,
        data_inicio=date(2041, 1, 1),
        data_fim=date(2041, 12, 31),
    )
    meso = Mesociclo(
        clube_id=clube_id,
        macrociclo=macro,
        numero=1,
        data_inicio=date(2041, 1, 1),
        data_fim=date(2041, 1, 31),
    )
    micro = Microciclo(
        clube_id=clube_id,
        mesociclo=meso,
        numero=1,
        data_inicio=date(2041, 1, 7),
        data_fim=date(2041, 1, 13),
    )
    sessao = SessaoTreino(
        clube_id=clube_id,
        microciclo=micro,
        data=date(2041, 1, 9),
        numero_treino=1,
        ativa=True,
    )
    db.add_all([equipa, jogadora_1, jogadora_2, macro, meso, micro, sessao])
    db.commit()
    return db, equipa.id, jogadora_1.id, jogadora_2.id, macro.id, sessao.id


def _limpar_contexto(db, equipa_id, jogador_ids, macro_id):
    db.query(AvaliacaoJogador).filter(AvaliacaoJogador.equipa_id == equipa_id).delete(synchronize_session=False)
    db.query(ParametroAvaliacao).filter(ParametroAvaliacao.equipa_id == equipa_id).delete(synchronize_session=False)
    macro = db.query(Macrociclo).filter(Macrociclo.id == macro_id).first()
    if macro:
        db.delete(macro)
    for jogador_id in jogador_ids:
        jogador = db.query(Jogador).filter(Jogador.id == jogador_id).first()
        if jogador:
            db.delete(jogador)
    equipa = db.query(Equipa).filter(Equipa.id == equipa_id).first()
    if equipa:
        db.delete(equipa)
    db.commit()


def test_painel_cria_parametros_base_e_apresenta_area_de_analise(client_admin):
    db, equipa_id, jogadora_1_id, jogadora_2_id, macro_id, _ = _criar_contexto()
    try:
        resposta = client_admin.get(f"/analise/equipas/{equipa_id}")
        assert resposta.status_code == 200
        assert "Análise de Desempenho" in resposta.text
        assert "dimensão técnica, tática, física e psicológica" in resposta.text
        assert "Observatório de desempenho" in resposta.text
        assert "data-analysis-period" in resposta.text
        assert "Matriz de parâmetros" in resposta.text
        assert "Resumo por atleta" in resposta.text
        assert "Ana Avaliação" in resposta.text
        assert db.query(ParametroAvaliacao).filter(ParametroAvaliacao.equipa_id == equipa_id).count() == 15
    finally:
        _limpar_contexto(db, equipa_id, [jogadora_1_id, jogadora_2_id], macro_id)
        db.close()


def test_avaliacao_multipla_guarda_e_atualiza_valores_da_sessao(client_admin):
    db, equipa_id, jogadora_1_id, jogadora_2_id, macro_id, sessao_id = _criar_contexto()
    try:
        client_admin.get(f"/analise/equipas/{equipa_id}")
        parametro = db.query(ParametroAvaliacao).filter(
            ParametroAvaliacao.equipa_id == equipa_id,
            ParametroAvaliacao.categoria == "tecnica",
        ).first()
        resposta = client_admin.post(
            f"/analise/equipas/{equipa_id}/registar",
            data={
                "data": "2041-01-09",
                "sessao_id": str(sessao_id),
                "jogador_ids": [str(jogadora_1_id), str(jogadora_2_id)],
                "parametro_ids": str(parametro.id),
                f"valor_{jogadora_1_id}_{parametro.id}": "4,5",
                f"valor_{jogadora_2_id}_{parametro.id}": "3",
            },
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resposta.status_code == 200
        assert resposta.json()["ok"] is True
        assert db.query(AvaliacaoJogador).filter(AvaliacaoJogador.sessao_id == sessao_id).count() == 2

        resposta = client_admin.post(
            f"/analise/equipas/{equipa_id}/registar",
            data={
                "data": "2041-01-09",
                "sessao_id": str(sessao_id),
                "jogador_ids": str(jogadora_1_id),
                "parametro_ids": str(parametro.id),
                f"valor_{jogadora_1_id}_{parametro.id}": "5",
            },
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resposta.status_code == 200
        registo = db.query(AvaliacaoJogador).filter(
            AvaliacaoJogador.sessao_id == sessao_id,
            AvaliacaoJogador.jogador_id == jogadora_1_id,
        ).one()
        assert registo.valor == 5
        assert db.query(AvaliacaoJogador).filter(AvaliacaoJogador.sessao_id == sessao_id).count() == 2

        detalhe = client_admin.get(f"/analise/jogadores/{jogadora_1_id}")
        assert detalhe.status_code == 200
        assert "Histórico completo" in detalhe.text
        assert "Desempenho ao longo do tempo" in detalhe.text
        assert f'data-player-locked="{jogadora_1_id}"' in detalhe.text
        assert "5" in detalhe.text

        ficha = client_admin.get(f"/jogadores/{jogadora_1_id}")
        assert ficha.status_code == 200
        assert 'data-workspace-tab="analise"' in ficha.text
        assert "Abrir histórico analítico completo" in ficha.text
    finally:
        _limpar_contexto(db, equipa_id, [jogadora_1_id, jogadora_2_id], macro_id)
        db.close()


def test_escala_tecnica_rejeita_valor_superior_a_cinco(client_admin):
    db, equipa_id, jogadora_1_id, jogadora_2_id, macro_id, sessao_id = _criar_contexto()
    try:
        client_admin.get(f"/analise/equipas/{equipa_id}")
        parametro = db.query(ParametroAvaliacao).filter(
            ParametroAvaliacao.equipa_id == equipa_id,
            ParametroAvaliacao.categoria == "tecnica",
        ).first()
        resposta = client_admin.post(
            f"/analise/equipas/{equipa_id}/registar",
            data={
                "data": "2041-01-09",
                "sessao_id": str(sessao_id),
                "jogador_ids": str(jogadora_1_id),
                "parametro_ids": str(parametro.id),
                f"valor_{jogadora_1_id}_{parametro.id}": "6",
            },
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resposta.status_code == 400
        assert resposta.json()["ok"] is False
        assert db.query(AvaliacaoJogador).filter(AvaliacaoJogador.equipa_id == equipa_id).count() == 0
    finally:
        _limpar_contexto(db, equipa_id, [jogadora_1_id, jogadora_2_id], macro_id)
        db.close()


def test_parametro_fisico_tem_unidade_e_limites_editaveis(client_admin):
    db, equipa_id, jogadora_1_id, jogadora_2_id, macro_id, _ = _criar_contexto()
    try:
        resposta = client_admin.post(
            f"/analise/equipas/{equipa_id}/parametros",
            data={
                "nome": "Sprint 20 m",
                "categoria": "fisica",
                "valor_minimo": "2,5",
                "valor_maximo": "6",
                "unidade": "s",
            },
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resposta.status_code == 200
        parametro = db.query(ParametroAvaliacao).filter(
            ParametroAvaliacao.equipa_id == equipa_id,
            ParametroAvaliacao.nome == "Sprint 20 m",
        ).one()
        assert parametro.valor_minimo == 2.5
        assert parametro.valor_maximo == 6
        assert parametro.unidade == "s"
        painel = client_admin.get(f"/analise/equipas/{equipa_id}#parametros")
        assert painel.status_code == 200
        assert "Sprint 20 m" in painel.text
    finally:
        _limpar_contexto(db, equipa_id, [jogadora_1_id, jogadora_2_id], macro_id)
        db.close()


def test_sessao_e_plano_de_treino_expoem_acesso_a_avaliacao(client_admin):
    db, equipa_id, jogadora_1_id, jogadora_2_id, macro_id, sessao_id = _criar_contexto()
    try:
        pagina = client_admin.get(f"/analise/equipas/{equipa_id}/registar?sessao_id={sessao_id}")
        assert pagina.status_code == 200
        assert "Associada ao treino 1" in pagina.text
        assert "data-step-indicator" in pagina.text

        plano = client_admin.get(f"/treino/sessoes/{sessao_id}")
        assert plano.status_code == 200
        assert f"/analise/equipas/{equipa_id}/registar?sessao_id={sessao_id}" in plano.text
        assert "Avaliar jogadores" in plano.text
    finally:
        _limpar_contexto(db, equipa_id, [jogadora_1_id, jogadora_2_id], macro_id)
        db.close()

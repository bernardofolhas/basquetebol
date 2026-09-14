from datetime import date

from database import SessionLocal
from models.assiduidade import ConvocacaoAssiduidade, RegistoAssiduidade
from models.avaliacao import AvaliacaoJogador, ParametroAvaliacao
from models.equipa import Equipa, EscalaoEnum, GeneroEnum
from models.estatistica import EventoEstatistica
from models.jogo import Convocado, Jogo
from models.jogador import Jogador
from models.planeamento import ConteudoSessaoTreino, Macrociclo, Mesociclo, Microciclo, SessaoTreino
from models.treino import ExercicioPlano, PlanoTreino
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
        assert "Mapa global de análise" in resposta.text
        assert "Treino, disponibilidade, competição e desempenho" in resposta.text
        assert "Categorias / exercícios" in resposta.text
        assert "Presenças / PSE" in resposta.text
        assert "Convocatórias" in resposta.text
        assert "Estatísticas de jogo" in resposta.text
        assert "Observatório de desempenho" in resposta.text
        assert "data-analysis-period" in resposta.text
        assert "Matriz de parâmetros" in resposta.text
        assert "Resumo por atleta" in resposta.text
        assert "Ana Avaliação" in resposta.text
        assert db.query(ParametroAvaliacao).filter(ParametroAvaliacao.equipa_id == equipa_id).count() == 15
    finally:
        _limpar_contexto(db, equipa_id, [jogadora_1_id, jogadora_2_id], macro_id)
        db.close()


def test_mapa_global_agrega_treino_presenca_convocatoria_e_estatisticas(client_admin):
    db, equipa_id, jogadora_1_id, jogadora_2_id, macro_id, sessao_id = _criar_contexto()
    jogo_id = None
    try:
        equipa = db.query(Equipa).filter(Equipa.id == equipa_id).one()
        sessao = db.query(SessaoTreino).filter(SessaoTreino.id == sessao_id).one()
        plano = PlanoTreino(clube_id=equipa.clube_id, sessao=sessao, hora_inicio="18:00")
        plano.exercicios.append(ExercicioPlano(
            clube_id=equipa.clube_id,
            nome="Finalização em vantagem",
            categoria="TIO",
            minutos=20,
            ordem=1,
        ))
        sessao.conteudos.append(ConteudoSessaoTreino(
            categoria="tecnica_individual_ofensiva",
            descricao="Finalização",
            minutos=20,
            ordem=1,
        ))
        db.add(RegistoAssiduidade(
            clube_id=equipa.clube_id,
            sessao=sessao,
            jogador_id=jogadora_1_id,
            presente=True,
            estado="presente",
            rpe_individual=7,
        ))
        jogo = Jogo(
            clube_id=equipa.clube_id,
            equipa_id=equipa_id,
            data=date(2041, 1, 12),
            adversario="Equipa Adversária",
            em_casa=True,
            pontos_nos=70,
            pontos_adversario=60,
        )
        jogo.convocados.append(Convocado(
            clube_id=equipa.clube_id,
            jogador_id=jogadora_1_id,
        ))
        db.add_all([plano, jogo])
        db.flush()
        jogo_id = jogo.id
        db.add(EventoEstatistica(
            client_uid=f"teste-analise-global-{equipa_id}",
            clube_id=equipa.clube_id,
            equipa_id=equipa_id,
            jogo_id=jogo.id,
            jogador_id=jogadora_1_id,
            lado="equipa",
            tipo="tres_c",
            periodo=1,
        ))
        db.commit()

        resposta = client_admin.get(f"/analise/equipas/{equipa_id}")
        assert resposta.status_code == 200
        assert "Finalização em vantagem" in resposta.text
        assert "20 min · 100.0%" in resposta.text
        assert "7.0" in resposta.text
        assert "Equipa Adversária" in resposta.text
        assert "Pontos marcados" in resposta.text
        assert ">3<" in resposta.text
    finally:
        if jogo_id:
            db.query(EventoEstatistica).filter(EventoEstatistica.jogo_id == jogo_id).delete(synchronize_session=False)
            jogo = db.query(Jogo).filter(Jogo.id == jogo_id).first()
            if jogo:
                db.delete(jogo)
        db.commit()
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
        presencas = db.query(RegistoAssiduidade).filter(
            RegistoAssiduidade.sessao_id == sessao_id,
        ).all()
        assert len(presencas) == 2
        assert all(item.presente and item.estado == "presente" for item in presencas)

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


def test_avaliacao_de_treino_preseleciona_apenas_atletas_presentes(client_admin):
    db, equipa_id, jogadora_1_id, jogadora_2_id, macro_id, sessao_id = _criar_contexto()
    try:
        clube_id = db.query(Equipa.clube_id).filter(Equipa.id == equipa_id).scalar()
        db.add_all([
            RegistoAssiduidade(
                clube_id=clube_id,
                sessao_id=sessao_id,
                jogador_id=jogadora_1_id,
                presente=True,
                estado="presente",
            ),
            RegistoAssiduidade(
                clube_id=clube_id,
                sessao_id=sessao_id,
                jogador_id=jogadora_2_id,
                presente=False,
                estado="ausente",
            ),
        ])
        db.commit()

        resposta = client_admin.get(f"/analise/equipas/{equipa_id}/registar?sessao_id={sessao_id}")
        assert resposta.status_code == 200
        primeira = resposta.text.split(f'data-player-selection="{jogadora_1_id}"', 1)[1].split("</label>", 1)[0]
        segunda = resposta.text.split(f'data-player-selection="{jogadora_2_id}"', 1)[1].split("</label>", 1)[0]
        assert "checked" in primeira
        assert "checked" not in segunda
        assert "1 atleta(s) presente(s) foram pré-selecionados" in resposta.text
    finally:
        _limpar_contexto(db, equipa_id, [jogadora_1_id, jogadora_2_id], macro_id)
        db.close()


def test_avaliacao_de_treino_inclui_e_guarda_convocado_de_outro_escalao(client_admin):
    db, equipa_id, jogadora_1_id, jogadora_2_id, macro_id, sessao_id = _criar_contexto()
    outra_equipa = None
    convocada = None
    try:
        equipa = db.query(Equipa).filter(Equipa.id == equipa_id).one()
        outra_equipa = Equipa(
            clube_id=equipa.clube_id,
            nome="Sub-16 Convocadas Avaliação",
            escalao=EscalaoEnum.sub16,
            genero=GeneroEnum.feminino,
        )
        convocada = Jogador(
            clube_id=equipa.clube_id,
            equipa=outra_equipa,
            nome="Carolina Convocada Avaliação",
            numero_camisola=12,
        )
        db.add_all([outra_equipa, convocada])
        db.flush()
        db.add(ConvocacaoAssiduidade(
            clube_id=equipa.clube_id,
            sessao_id=sessao_id,
            jogador_id=convocada.id,
        ))
        db.commit()
        convocada_id = convocada.id

        pagina = client_admin.get(f"/analise/equipas/{equipa_id}/registar?sessao_id={sessao_id}")
        assert pagina.status_code == 200
        assert f'data-player-selection="{convocada_id}"' in pagina.text
        assert "Carolina Convocada Avaliação" in pagina.text
        assert "Convocado · Sub-16 Convocadas Avaliação" in pagina.text

        pagina_sem_sessao = client_admin.get(f"/analise/equipas/{equipa_id}/registar")
        assert pagina_sem_sessao.status_code == 200
        assert f'data-player-selection="{convocada_id}"' not in pagina_sem_sessao.text

        parametro = db.query(ParametroAvaliacao).filter(
            ParametroAvaliacao.equipa_id == equipa_id,
            ParametroAvaliacao.categoria == "tecnica",
        ).first()
        resposta = client_admin.post(
            f"/analise/equipas/{equipa_id}/registar",
            data={
                "data": "2041-01-09",
                "sessao_id": str(sessao_id),
                "jogador_ids": str(convocada_id),
                "parametro_ids": str(parametro.id),
                f"valor_{convocada_id}_{parametro.id}": "4",
            },
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resposta.status_code == 200
        assert resposta.json()["ok"] is True
        avaliacao = db.query(AvaliacaoJogador).filter(
            AvaliacaoJogador.equipa_id == equipa_id,
            AvaliacaoJogador.sessao_id == sessao_id,
            AvaliacaoJogador.jogador_id == convocada_id,
        ).one()
        assert avaliacao.valor == 4
    finally:
        if convocada is not None:
            db.query(ConvocacaoAssiduidade).filter(
                ConvocacaoAssiduidade.jogador_id == convocada.id,
            ).delete(synchronize_session=False)
            db.query(RegistoAssiduidade).filter(
                RegistoAssiduidade.jogador_id == convocada.id,
            ).delete(synchronize_session=False)
            db.query(AvaliacaoJogador).filter(
                AvaliacaoJogador.jogador_id == convocada.id,
            ).delete(synchronize_session=False)
            db.delete(convocada)
        if outra_equipa is not None:
            db.delete(outra_equipa)
        db.commit()
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

        resposta_normal = client_admin.post(
            f"/analise/equipas/{equipa_id}/parametros",
            data={
                "nome": "Leitura sem bola",
                "categoria": "tatica",
                "valor_minimo": "0",
                "valor_maximo": "5",
            },
            follow_redirects=False,
        )
        assert resposta_normal.status_code == 303
        assert resposta_normal.headers["location"] == f"/analise/equipas/{equipa_id}#parametros"
        assert db.query(ParametroAvaliacao).filter(
            ParametroAvaliacao.equipa_id == equipa_id,
            ParametroAvaliacao.nome == "Leitura sem bola",
        ).count() == 1

        painel = client_admin.get(f"/analise/equipas/{equipa_id}#parametros")
        assert 'id="form-novo-parametro"' in painel.text
        assert "data-parameter-submit" in painel.text
        assert "data-parameter-feedback" in painel.text

        eliminar = client_admin.post(
            f"/analise/parametros/{parametro.id}/eliminar",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert eliminar.status_code == 200
        assert eliminar.json()["ok"] is True
        db.refresh(parametro)
        assert parametro.ativo is False

        pagina_avaliacao = client_admin.get(f"/analise/equipas/{equipa_id}/registar")
        assert f'data-parameter-option-row="{parametro.id}"' not in pagina_avaliacao.text
        assert "data-delete-evaluation-parameter" in pagina_avaliacao.text
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
        assert "ds-eval-player-card" in pagina.text
        assert "data-player-photo" in pagina.text
        assert 'id="dialog-evaluation-value"' in pagina.text
        assert "ds-eval-scale-option" in pagina.text
        assert "Toca num número da escala" in pagina.text
        assert "X-CSRF-Token" in pagina.text
        assert "const form = event.currentTarget" in pagina.text
        assert "event.currentTarget.querySelectorAll('input[name^=\"valor_\"]')" not in pagina.text

        plano = client_admin.get(f"/treino/sessoes/{sessao_id}")
        assert plano.status_code == 200
        assert f"/analise/equipas/{equipa_id}/registar?sessao_id={sessao_id}" in plano.text
        assert "Avaliar jogadores" in plano.text
    finally:
        _limpar_contexto(db, equipa_id, [jogadora_1_id, jogadora_2_id], macro_id)
        db.close()

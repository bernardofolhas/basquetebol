from models.planeamento import Macrociclo, Mesociclo, Microciclo, SessaoTreino
from models.treino import BibliotecoExercicio, PlanoTreino, ExercicioPlano
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


def test_adicionar_exercicio_aparece_imediatamente_depois_dos_cartoes(client_admin):
    db, equipa_id, jogador_id, outro_id, macro_id = _criar_contexto()
    try:
        sessao = db.query(SessaoTreino).join(Microciclo).join(Mesociclo).join(Macrociclo).filter(
            Macrociclo.id == macro_id
        ).one()
        client_admin.get(f"/treino/sessoes/{sessao.id}")
        plano = db.query(PlanoTreino).filter_by(sessao_id=sessao.id).one()
        for nome in ("Primeiro exercício", "Último exercício"):
            resposta = client_admin.post(
                f"/treino/planos/{plano.id}/exercicios",
                data={"nome": nome, "minutos": "10"},
                follow_redirects=False,
            )
            assert resposta.status_code == 303

        pagina = client_admin.get(f"/treino/sessoes/{sessao.id}")
        assert pagina.status_code == 200
        ultimo_cartao = pagina.text.rfind('<article id="exercicio-')
        fluxo_adicionar = pagina.text.index('data-training-add-flow')
        painel_adicionar = pagina.text.index('id="training-add-panel"', fluxo_adicionar)
        separador_adicionar = pagina.text.index('class="training-add-divider"', painel_adicionar)
        botao_adicionar = pagina.text.index('data-training-add><span', separador_adicionar)
        assert ultimo_cartao < fluxo_adicionar < painel_adicionar < separador_adicionar < botao_adicionar
        assert 'class="training-add-trigger"' in pagina.text[separador_adicionar:botao_adicionar]
        assert pagina.text.count('aria-controls="training-add-panel"') == 1
        assert pagina.text.count('id="form_adicionar_exercicio"') == 1
    finally:
        _limpar_contexto(db, equipa_id, jogador_id, outro_id, macro_id)
        db.close()


def test_alterar_horario_da_sessao_recalcula_horas_dos_exercicios(client_admin):
    db, equipa_id, jogador_id, outro_id, macro_id = _criar_contexto()
    try:
        sessao = db.query(SessaoTreino).join(Microciclo).join(Mesociclo).join(Macrociclo).filter(
            Macrociclo.id == macro_id
        ).one()
        client_admin.get(f"/treino/sessoes/{sessao.id}")
        plano = db.query(PlanoTreino).filter_by(sessao_id=sessao.id).one()
        for nome, minutos in (("Primeiro", 15), ("Segundo", 20)):
            client_admin.post(
                f"/treino/planos/{plano.id}/exercicios",
                data={"nome": nome, "minutos": str(minutos)},
                follow_redirects=False,
            )

        resposta = client_admin.post(
            f"/treino/planos/{plano.id}/cabecalho",
            data={
                "hora_inicio": "19:30",
                "hora_fim": "21:00",
                "local": "Pavilhão",
                "escalao": "Sub-18",
                "objectivos": "",
                "intensidade_rpe": "7",
            },
            follow_redirects=False,
        )

        assert resposta.status_code == 303
        db.expire_all()
        exercicios = db.query(ExercicioPlano).filter_by(plano_id=plano.id).order_by(ExercicioPlano.ordem).all()
        assert [(ex.hora, ex.minutos) for ex in exercicios] == [
            ("19:30", 15),
            ("19:45", 20),
        ]
    finally:
        _limpar_contexto(db, equipa_id, jogador_id, outro_id, macro_id)
        db.close()


def test_cabecalho_sincroniza_evento_de_agenda_e_sessoes_ligadas(client_admin):
    db, equipa_id, jogador_id, outro_id, macro_id = _criar_contexto()
    evento = None
    try:
        from models.planeamento_clube import EventoPlaneamentoClube, TipoEventoPlaneamentoClubeEnum

        sessao = db.query(SessaoTreino).join(Microciclo).join(Mesociclo).join(Macrociclo).filter(
            Macrociclo.id == macro_id
        ).one()
        client_admin.get(f"/treino/sessoes/{sessao.id}")
        plano = db.query(PlanoTreino).filter_by(sessao_id=sessao.id).one()
        client_admin.post(
            f"/treino/planos/{plano.id}/exercicios",
            data={"nome": "Exercício ligado", "minutos": "15"},
            follow_redirects=False,
        )

        evento = EventoPlaneamentoClube(
            clube_id=sessao.clube_id,
            equipa_id=equipa_id,
            tipo=TipoEventoPlaneamentoClubeEnum.treino_equipa,
            titulo="Treino da agenda",
            data=sessao.data,
            hora_inicio="18:00",
            hora_fim="19:00",
        )
        db.add(evento)
        db.flush()
        sessao.evento_planeamento_clube = evento
        db.commit()

        resposta = client_admin.post(
            f"/treino/planos/{plano.id}/cabecalho",
            data={"hora_inicio": "20:00", "hora_fim": "21:00", "intensidade_rpe": "7"},
            follow_redirects=False,
        )

        assert resposta.status_code == 303
        db.expire_all()
        evento = db.query(EventoPlaneamentoClube).filter_by(id=evento.id).one()
        sessao = db.query(SessaoTreino).filter_by(id=sessao.id).one()
        exercicio = db.query(ExercicioPlano).filter_by(plano_id=plano.id).one()
        assert (evento.hora_inicio, evento.hora_fim) == ("20:00", "21:00")
        assert (sessao.hora_inicio, sessao.hora_fim, exercicio.hora) == ("20:00", "21:00", "20:00")
    finally:
        if evento is not None:
            db.query(EventoPlaneamentoClube).filter_by(id=evento.id).delete(synchronize_session=False)
            db.commit()
        _limpar_contexto(db, equipa_id, jogador_id, outro_id, macro_id)
        db.close()


def test_biblioteca_recebe_novo_exercicio_e_reutilizacao_fica_independente(client_admin):
    db, equipa_id, jogador_id, outro_id, macro_id = _criar_contexto()
    try:
        sessao = db.query(SessaoTreino).join(Microciclo).join(Mesociclo).join(Macrociclo).filter(
            Macrociclo.id == macro_id
        ).one()
        client_admin.get(f"/treino/sessoes/{sessao.id}")
        plano = db.query(PlanoTreino).filter_by(sessao_id=sessao.id).one()
        nome_original = f"Exercicio base {macro_id}"

        resposta = client_admin.post(
            f"/treino/planos/{plano.id}/exercicios",
            data={
                "nome": nome_original,
                "categoria": "TIO",
                "minutos": "12",
                "organizacao": "Organizacao original",
                "coaching_points": "Coaching original",
            },
            follow_redirects=False,
        )
        assert resposta.status_code == 303
        base = db.query(BibliotecoExercicio).filter_by(
            clube_id=plano.clube_id,
            nome=nome_original,
        ).one()
        assert (base.categoria, base.organizacao, base.coaching_points) == (
            "TIO", "Organizacao original", "Coaching original"
        )
        total_biblioteca_antes_da_copia = db.query(BibliotecoExercicio).filter_by(
            clube_id=plano.clube_id,
        ).count()

        nome_copia = f"Copia adaptada {macro_id}"
        resposta = client_admin.post(
            f"/treino/planos/{plano.id}/exercicios",
            data={
                "biblioteca_id": str(base.id),
                "origem_biblioteca": "biblioteca",
                "nome": nome_copia,
                "categoria": "TCO",
                "minutos": "20",
                "organizacao": "Organizacao so deste treino",
                "coaching_points": "Coaching so deste treino",
            },
            follow_redirects=False,
        )
        assert resposta.status_code == 303
        db.expire_all()

        base = db.query(BibliotecoExercicio).filter_by(id=base.id).one()
        assert (base.nome, base.categoria, base.organizacao, base.coaching_points) == (
            nome_original, "TIO", "Organizacao original", "Coaching original"
        )
        assert db.query(BibliotecoExercicio).filter_by(
            clube_id=plano.clube_id,
        ).count() == total_biblioteca_antes_da_copia
        assert db.query(BibliotecoExercicio).filter_by(
            clube_id=plano.clube_id,
            nome=nome_copia,
        ).count() == 0
        copia = db.query(ExercicioPlano).filter_by(plano_id=plano.id, nome=nome_copia).one()
        assert (copia.categoria, copia.minutos, copia.organizacao, copia.coaching_points) == (
            "TCO", 20, "Organizacao so deste treino", "Coaching so deste treino"
        )

        resposta = client_admin.post(
            f"/treino/exercicios/{copia.id}/atualizar",
            data={
                "nome": f"Versao final {macro_id}",
                "categoria": "TID",
                "hora": copia.hora or "",
                "minutos": "25",
                "organizacao": "Alterada novamente no plano",
                "coaching_points": "Sem tocar na biblioteca",
            },
            follow_redirects=False,
        )
        assert resposta.status_code == 303
        db.expire_all()
        base = db.query(BibliotecoExercicio).filter_by(id=base.id).one()
        assert (base.nome, base.categoria, base.organizacao, base.coaching_points) == (
            nome_original, "TIO", "Organizacao original", "Coaching original"
        )
        assert db.query(BibliotecoExercicio).filter_by(
            clube_id=plano.clube_id,
            nome=f"Versao final {macro_id}",
        ).count() == 0
        assert db.query(BibliotecoExercicio).filter_by(
            clube_id=plano.clube_id,
        ).count() == total_biblioteca_antes_da_copia
    finally:
        _limpar_contexto(db, equipa_id, jogador_id, outro_id, macro_id)
        db.close()


def test_reordenar_exercicios_atualiza_ordem_e_horas_sem_redirect(client_admin):
    db, equipa_id, jogador_id, outro_id, macro_id = _criar_contexto()
    try:
        sessao = db.query(SessaoTreino).join(Microciclo).join(Mesociclo).join(Macrociclo).filter(
            Macrociclo.id == macro_id
        ).one()
        client_admin.get(f"/treino/sessoes/{sessao.id}")
        plano = db.query(PlanoTreino).filter_by(sessao_id=sessao.id).one()

        for nome, minutos in (("Primeiro", 10), ("Segundo", 15), ("Terceiro", 20)):
            client_admin.post(
                f"/treino/planos/{plano.id}/exercicios",
                data={"nome": nome, "minutos": str(minutos)},
                follow_redirects=False,
            )

        exercicios = db.query(ExercicioPlano).filter_by(plano_id=plano.id).order_by(ExercicioPlano.ordem).all()
        resposta = client_admin.post(
            f"/treino/planos/{plano.id}/exercicios/reordenar",
            json={"exercicio_ids": [exercicios[2].id, exercicios[0].id, exercicios[1].id]},
        )

        assert resposta.status_code == 200
        assert resposta.json()["sucesso"] is True
        assert resposta.json()["proxima_hora"] == "18:45"
        db.expire_all()
        reordenados = db.query(ExercicioPlano).filter_by(plano_id=plano.id).order_by(ExercicioPlano.ordem).all()
        assert [(ex.nome, ex.hora, ex.ordem) for ex in reordenados] == [
            ("Terceiro", "18:00", 1),
            ("Primeiro", "18:20", 2),
            ("Segundo", "18:30", 3),
        ]
        pagina = client_admin.get(f"/treino/sessoes/{sessao.id}")
        assert 'name="hora" value="18:45" data-training-next-time' in pagina.text

        invalida = client_admin.post(
            f"/treino/planos/{plano.id}/exercicios/reordenar",
            json={"exercicio_ids": [reordenados[0].id, reordenados[0].id, reordenados[2].id]},
        )
        assert invalida.status_code == 422
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
        assert 'data-training-exercise-drag' in pagina.text
        assert 'draggable="true"' not in pagina.text
        assert "function posicionarCartao" in pagina.text
        assert "document.addEventListener('pointermove'" in pagina.text
        assert "document.addEventListener('pointerup'" in pagina.text
        assert "setPointerCapture" in pagina.text
        assert "root.addEventListener('dragstart'" not in pagina.text
        assert "rect.top + rect.height / 2" in pagina.text
        assert 'data-training-reorder-url=' in pagina.text
        assert "referencia.getBoundingClientRect()" in pagina.text
        assert "atualizarHorasNoEcra()" in pagina.text
        assert "getCoalescedEvents" in pagina.text
        assert 'data-drawing-preview=' in pagina.text
        assert '<figcaption>' not in pagina.text
        assert 'data-drawing-editor' in pagina.text
        assert "adicionarCampoSemRecarregar(event, this" in pagina.text
        assert "removerCampoSemRecarregar(event, this" in pagina.text
        assert 'data-court-template="meio"' in pagina.text
        assert "est.ctx.drawImage(est.imagemFundo" in pagina.text
        assert 'action="/treino/exercicios/' in pagina.text
        assert "/notas" in pagina.text
        assert "Editar dados do exercício" not in pagina.text

        exercicio = db.query(ExercicioPlano).filter_by(plano_id=plano.id).one()
        novo_campo = client_admin.post(
            f"/treino/exercicios/{exercicio.id}/campos",
            data={"tipo": "meio"},
            headers={"Accept": "application/json"},
        )
        assert novo_campo.status_code == 200
        assert novo_campo.json() == {
            "sucesso": True,
            "campo": {
                "numero": 3,
                "tipo": "meio",
                "label": "Campo meio 2",
                "imagem": "campo_meio.png?v=20260908-madeira-1",
            },
        }
        campo_removido = client_admin.post(
            f"/treino/exercicios/{exercicio.id}/campos/3/apagar",
            headers={"Accept": "application/json"},
        )
        assert campo_removido.status_code == 200
        assert campo_removido.json() == {"sucesso": True, "numero": 3}
        db.refresh(exercicio)
        assert "3" not in (exercicio.campos_ativos or "").split(",")
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
        assert '<div class="court-card">\n                    <h5>' not in pagina.text
    finally:
        _limpar_contexto(db, equipa_id, jogador_id, outro_id, macro_id)
        db.close()

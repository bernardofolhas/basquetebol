from datetime import date, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from database import SessionLocal
from models.equipa import Equipa
from models.jogo import ItemPlanoJogoBiblioteca, Jogo, PlanoJogoItem
from models.playbook import PassoSetPlay, Playbook, SetPlay
from models.scouting import (
    ScoutingAdversario,
    ScoutingAdversarioJogo,
    ScoutingGrupoAvaliacao,
    ScoutingItemBiblioteca,
    ScoutingJogador,
    ScoutingJogadorItem,
    ScoutingMediaColetiva,
    ScoutingOpcoesDefensivas,
)
from models.utilizador import Utilizador
from paths import TEMPLATES_DIR
from template_config import Jinja2Templates


ROOT = Path(__file__).resolve().parents[2]


def test_scouting_mantem_modelos_e_migracao_por_jogo():
    modelo = (ROOT / "backend" / "models" / "scouting.py").read_text(encoding="utf-8")
    migracao = (
        ROOT / "backend" / "migrations" / "versions" / "0027_scouting.py"
    ).read_text(encoding="utf-8")
    jogo = (ROOT / "backend" / "models" / "jogo.py").read_text(encoding="utf-8")

    assert 'class RelatorioScouting' in modelo
    assert '__tablename__ = "relatorios_scouting"' in modelo
    assert 'ForeignKey("jogos.id", ondelete="CASCADE")' in modelo
    assert 'unique=True' in modelo
    assert 'relatorios_scouting' in migracao
    assert 'scouting = relationship(' in jogo


def test_scouting_e_plano_de_jogo_estao_acessiveis_no_fluxo_de_jogos():
    tabs = (TEMPLATES_DIR / "scouting" / "_departamento_tabs.html").read_text(encoding="utf-8")
    detalhe_jogo = (TEMPLATES_DIR / "jogos" / "detalhe.html").read_text(
        encoding="utf-8"
    )

    assert "Plano de Jogo" in tabs
    assert "plano-jogo" in tabs
    assert 'data-workspace-tab="scouting"' in detalhe_jogo
    assert 'Abrir scouting' in detalhe_jogo


def test_variantes_de_botao_isoladas_mantem_estrutura_visual():
    estilos = (ROOT / "frontend" / "static" / "css" / "design-system.css").read_text(
        encoding="utf-8"
    )

    assert ".ds-button-primary:not(.ds-button)" in estilos
    assert ".ds-button-secondary:not(.ds-button)" in estilos
    assert "Variantes usadas isoladamente" in estilos


def test_templates_de_scouting_renderizam_no_ambiente_jinja():
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    for nome in (
        "scouting/detalhe.html",
        "scouting/pdf_tecnico.html",
        "scouting/pdf_resumo_tecnico.html",
        "scouting/pdf_atletas_resumo.html",
        "scouting/pdf_atletas.html",
    ):
        templates.env.get_template(nome)


def test_departamento_scouting_tem_modelo_permanente_e_dados_separados():
    modelo = (ROOT / "backend" / "models" / "scouting.py").read_text(encoding="utf-8")
    migracao = (ROOT / "backend" / "migrations" / "versions" / "0047_departamento_scouting.py").read_text(encoding="utf-8")

    for classe in (
        "ScoutingAdversario", "ScoutingAdversarioJogo", "ScoutingJogador",
        "ScoutingFichaIndividual", "ScoutingMediaEpoca", "ScoutingEstatisticaJogo",
        "ScoutingItemBiblioteca", "ScoutingJogadorItem", "ScoutingZonaAcao",
    ):
        assert f"class {classe}" in modelo
    for tabela in (
        "scouting_adversarios", "scouting_roster_jogadores", "scouting_fichas_individuais",
        "scouting_medias_epoca", "scouting_estatisticas_jogo", "scouting_biblioteca_itens",
        "scouting_zonas_acao",
    ):
        assert tabela in migracao


def test_departamento_scouting_expoe_tabs_roster_e_ficha_individual():
    tabs = (TEMPLATES_DIR / "scouting" / "_departamento_tabs.html").read_text(encoding="utf-8")
    roster = (TEMPLATES_DIR / "scouting" / "roster.html").read_text(encoding="utf-8")
    campos = (TEMPLATES_DIR / "scouting" / "_roster_fields.html").read_text(encoding="utf-8")
    individual = (TEMPLATES_DIR / "scouting" / "individual.html").read_text(encoding="utf-8")

    for titulo in ("Resumo", "Roster", "Scouting Individual", "Scouting Coletivo", "Plano de Jogo", "Relatórios"):
        assert titulo in tabs
    for nome in ("fotografia", "posicao_principal", "posicao_alternativa", "altura_cm", "peso_kg", "estado", "mao_dominante"):
        assert f'name="{nome}"' in campos
    assert 'action="/scouting/roster/' in roster
    assert "Média da época vs. jogo selecionado" in individual
    inteligencia = (TEMPLATES_DIR / "scouting" / "_individual_intelligence.html").read_text(encoding="utf-8")
    assert "biblioteca reutilizável" in inteligencia.lower()
    assert "Perfil operacional do jogador" in inteligencia
    assert 'name="zonas"' in individual
    assert "campo_meio.png" in individual


def test_scouting_entra_na_area_de_analise_e_jogos_abrem_dossier():
    navbar = (TEMPLATES_DIR / "partials" / "navbar_global.html").read_text(encoding="utf-8")
    router = (ROOT / "backend" / "routers" / "scouting.py").read_text(encoding="utf-8")

    assert "Adversários, roster e análise individual" in navbar
    assert "ScoutingAdversarioJogo.jogo_id == jogo.id" in router
    assert 'url=f"/scouting/adversarios/{ligacao.adversario_id}/resumo"' in router


def test_departamento_scouting_abre_para_administrador(client_admin):
    resposta = client_admin.get("/scouting")

    assert resposta.status_code == 200
    assert "Scouting de adversários" in resposta.text
    assert "Roster permanente" in resposta.text


def _criar_adversario_integracao():
    db = SessionLocal()
    try:
        administrador = db.query(Utilizador).filter(Utilizador.username == "admin").first()
        if not administrador or not administrador.clube_id:
            pytest.skip("Conta administrativa de teste sem clube.")
        equipa = db.query(Equipa).filter(Equipa.clube_id == administrador.clube_id).first()
        if not equipa:
            pytest.skip("Clube de teste sem equipa.")

        sufixo = uuid4().hex[:10]
        nome = f"Adversário integração {sufixo}"
        jogo = Jogo(
            clube_id=administrador.clube_id,
            equipa_id=equipa.id,
            data=date(2042, 9, 16),
            hora="20:00",
            adversario=nome,
            em_casa=True,
        )
        adversario = ScoutingAdversario(
            clube_id=administrador.clube_id,
            nome=nome,
            nome_normalizado=nome.lower(),
        )
        db.add_all((jogo, adversario))
        db.flush()
        db.add(ScoutingAdversarioJogo(
            clube_id=administrador.clube_id,
            adversario_id=adversario.id,
            jogo_id=jogo.id,
        ))
        db.commit()
        return adversario.id, jogo.id, equipa.id, administrador.clube_id, nome
    finally:
        db.close()


def _eliminar_adversario_integracao(adversario_id, jogo_id, playbook_id=None):
    db = SessionLocal()
    try:
        adversario = db.query(ScoutingAdversario).filter(ScoutingAdversario.id == adversario_id).first()
        if adversario:
            db.delete(adversario)
            db.flush()
        if playbook_id:
            playbook = db.query(Playbook).filter(Playbook.id == playbook_id).first()
            if playbook:
                db.delete(playbook)
                db.flush()
        jogo = db.query(Jogo).filter(Jogo.id == jogo_id).first()
        if jogo:
            db.delete(jogo)
        db.commit()
    finally:
        db.close()


def test_coletivo_abre_e_exporta_leitura_facil(client_admin):
    adversario_id, jogo_id, _, _, _ = _criar_adversario_integracao()
    try:
        pagina = client_admin.get(f"/scouting/adversarios/{adversario_id}/coletivo")
        assert pagina.status_code == 200
        assert "Prepara a leitura fácil" in pagina.text
        assert "Perfil coletivo 0–5" in pagina.text

        configurador = client_admin.get(f"/exportacoes/relatorios/scouting-coletivo/{adversario_id}")
        assert configurador.status_code == 200

        dados = {"formato": "facil", "secoes": ["identidade", "chaves", "cinco_rotacao", "estatisticas", "perfil", "resposta", "diagramas"]}
        previsualizacao = client_admin.post(f"/exportacoes/relatorios/scouting-coletivo/{adversario_id}/previsualizar", data=dados)
        assert previsualizacao.status_code == 200
        assert "Scouting Coletivo" in previsualizacao.text

        pdf = client_admin.post(f"/exportacoes/relatorios/scouting-coletivo/{adversario_id}/pdf", data=dados)
        assert pdf.status_code == 200
        assert pdf.content.startswith(b"%PDF")
    finally:
        _eliminar_adversario_integracao(adversario_id, jogo_id)


def test_scouting_escolhe_proximo_jogo_e_bloqueia_jogos_passados(client_admin):
    adversario_id, jogo_passado_id, equipa_id, clube_id, nome = _criar_adversario_integracao()
    jogos_extra_ids = []
    hoje = date.today()
    try:
        db = SessionLocal()
        try:
            jogo_passado = db.get(Jogo, jogo_passado_id)
            jogo_passado.data = hoje - timedelta(days=1)
            jogo_passado.hora = "21:00"
            for dias, hora in ((8, "20:00"), (3, "18:00")):
                jogo = Jogo(
                    clube_id=clube_id,
                    equipa_id=equipa_id,
                    data=hoje + timedelta(days=dias),
                    hora=hora,
                    adversario=nome,
                    em_casa=True,
                )
                db.add(jogo)
                db.flush()
                jogos_extra_ids.append(jogo.id)
                db.add(ScoutingAdversarioJogo(
                    clube_id=clube_id,
                    adversario_id=adversario_id,
                    jogo_id=jogo.id,
                ))
            db.commit()
        finally:
            db.close()

        jogo_distante_id, jogo_proximo_id = jogos_extra_ids
        resposta = client_admin.get(f"/scouting/adversarios/{adversario_id}/plano-jogo")
        assert resposta.status_code == 200
        assert resposta.text.index(f'value="{jogo_proximo_id}" selected') < resposta.text.index(f'value="{jogo_distante_id}"')

        relatorios = client_admin.get(f"/scouting/adversarios/{adversario_id}/relatorios")
        assert relatorios.status_code == 200
        assert (hoje - timedelta(days=1)).strftime("%d/%m/%Y") not in relatorios.text
        assert f"data-report-options='[{jogo_proximo_id}, {jogo_distante_id}]'" in relatorios.text

        bloqueado = client_admin.get(f"/jogos/{jogo_passado_id}/plano", follow_redirects=False)
        assert bloqueado.status_code == 303
        assert bloqueado.headers["location"] == f"/jogos/{jogo_passado_id}"

        exportacao = client_admin.get(
            f"/exportacoes/relatorios/plano-jogo/{jogo_passado_id}",
            follow_redirects=False,
        )
        assert exportacao.status_code == 409
    finally:
        _eliminar_adversario_integracao(adversario_id, jogo_passado_id)
        db = SessionLocal()
        try:
            for jogo_id in jogos_extra_ids:
                jogo = db.get(Jogo, jogo_id)
                if jogo:
                    db.delete(jogo)
            db.commit()
        finally:
            db.close()


def test_primeira_abertura_do_scouting_coletivo_cria_dependencias_sem_erro(client_admin):
    adversario_id, jogo_id, _, clube_id, _ = _criar_adversario_integracao()
    try:
        resposta = client_admin.get(f"/scouting/adversarios/{adversario_id}/coletivo")

        assert resposta.status_code == 200
        assert "Scouting Coletivo" in resposta.text

        db = SessionLocal()
        try:
            media = db.query(ScoutingMediaColetiva).filter(
                ScoutingMediaColetiva.adversario_id == adversario_id
            ).one()
            opcoes = db.query(ScoutingOpcoesDefensivas).filter(
                ScoutingOpcoesDefensivas.adversario_id == adversario_id
            ).one()
            assert media.clube_id == clube_id
            assert opcoes.clube_id == clube_id
        finally:
            db.close()
    finally:
        _eliminar_adversario_integracao(adversario_id, jogo_id)


def test_conceito_ofensivo_abre_playbook_studio_com_cena_valida(client_admin):
    adversario_id, jogo_id, _, clube_id, nome_adversario = _criar_adversario_integracao()
    playbook_id = None
    try:
        criacao = client_admin.post(
            f"/scouting/adversarios/{adversario_id}/coletivo/conceitos",
            data={"titulo": "Saída horns", "observacoes": "Primeira leitura"},
            follow_redirects=False,
        )
        assert criacao.status_code == 303
        assert criacao.headers["location"].startswith("/playbook/studio/setplays/")

        setplay_id = int(criacao.headers["location"].rsplit("/", 1)[-1])
        studio = client_admin.get(criacao.headers["location"])
        assert studio.status_code == 200
        assert "Playbook Studio" in studio.text
        assert "Saída horns" in studio.text

        db = SessionLocal()
        try:
            setplay = db.query(SetPlay).filter(SetPlay.id == setplay_id).one()
            passo = db.query(PassoSetPlay).filter(PassoSetPlay.setplay_id == setplay.id).one()
            playbook_id = setplay.playbook_id
            assert setplay.clube_id == clube_id
            assert passo.clube_id == clube_id
            assert setplay.playbook.nome == f"Scouting · {nome_adversario}"
            passo.desenho = '{"formato":"desenho-tatico-v1","imagem":{},"estado":{}}'
            db.commit()
        finally:
            db.close()

        coletivo = client_admin.get(f"/scouting/adversarios/{adversario_id}/coletivo")
        studio_com_desenho_antigo = client_admin.get(criacao.headers["location"])
        assert coletivo.status_code == 200
        assert studio_com_desenho_antigo.status_code == 200
    finally:
        _eliminar_adversario_integracao(adversario_id, jogo_id, playbook_id)


def test_movimento_especifico_e_associado_sem_bloquear_ficha(client_admin):
    adversario_id, jogo_id, _, clube_id, _ = _criar_adversario_integracao()
    nome_movimento = f"Movimento específico {uuid4().hex[:8]}"
    jogador_id = None
    try:
        db = SessionLocal()
        try:
            jogador = ScoutingJogador(
                clube_id=clube_id,
                adversario_id=adversario_id,
                nome="Atleta Académica",
                numero="7",
                posicao_principal="Base",
            )
            db.add(jogador)
            db.commit()
            jogador_id = jogador.id
        finally:
            db.close()

        resposta = client_admin.post(
            f"/scouting/jogadores/{jogador_id}/itens",
            data={
                "categoria": "movimento",
                "nome_novo": nome_movimento,
                "observacao": "Leitura específica",
            },
            follow_redirects=True,
        )

        assert resposta.status_code == 200
        assert nome_movimento in resposta.text
        db = SessionLocal()
        try:
            item = db.query(ScoutingItemBiblioteca).filter(
                ScoutingItemBiblioteca.clube_id == clube_id,
                ScoutingItemBiblioteca.nome == nome_movimento,
            ).one()
            associacao = db.query(ScoutingJogadorItem).filter(
                ScoutingJogadorItem.jogador_id == jogador_id,
                ScoutingJogadorItem.item_id == item.id,
            ).one()
            assert associacao.observacao == "Leitura específica"
        finally:
            db.close()
    finally:
        _eliminar_adversario_integracao(adversario_id, jogo_id)
        db = SessionLocal()
        try:
            item = db.query(ScoutingItemBiblioteca).filter(
                ScoutingItemBiblioteca.clube_id == clube_id,
                ScoutingItemBiblioteca.nome == nome_movimento,
            ).first()
            if item:
                db.delete(item)
                db.commit()
        finally:
            db.close()


def test_perfil_individual_estrutura_avaliacao_tendencia_game_plan_e_importacao(client_admin):
    adversario_id, jogo_id, _, clube_id, _ = _criar_adversario_integracao()
    sufixo = uuid4().hex[:8]
    jogador_id = grupo_id = caracteristica_id = tendencia_id = game_plan_id = None
    try:
        db = SessionLocal()
        try:
            jogador = ScoutingJogador(
                clube_id=clube_id,
                adversario_id=adversario_id,
                nome=f"Atleta KYP {sufixo}",
                numero="11",
                posicao_principal="Extremo",
            )
            db.add(jogador)
            db.commit()
            jogador_id = jogador.id
        finally:
            db.close()

        resposta = client_admin.post(
            f"/scouting/jogadores/{jogador_id}/grupos-avaliacao",
            data={"nome": f"Shooting {sufixo}"},
            follow_redirects=False,
        )
        assert resposta.status_code == 303

        db = SessionLocal()
        try:
            grupo = db.query(ScoutingGrupoAvaliacao).filter(
                ScoutingGrupoAvaliacao.clube_id == clube_id,
                ScoutingGrupoAvaliacao.nome == f"Shooting {sufixo}",
            ).one()
            grupo_id = grupo.id
        finally:
            db.close()

        resposta = client_admin.post(
            f"/scouting/jogadores/{jogador_id}/itens",
            data={
                "categoria": "caracteristica",
                "nome_novo": f"Catch and Shoot {sufixo}",
                "grupo_id": str(grupo_id),
                "avaliacao": "4",
                "observacao": "Liberta rápido após kick-out.",
                "destaque": "true",
            },
            follow_redirects=True,
        )
        assert resposta.status_code == 200
        assert "4/5" in resposta.text

        db = SessionLocal()
        try:
            caracteristica = db.query(ScoutingJogadorItem).join(ScoutingItemBiblioteca).filter(
                ScoutingJogadorItem.jogador_id == jogador_id,
                ScoutingItemBiblioteca.categoria == "caracteristica",
            ).one()
            caracteristica_id = caracteristica.id
            assert caracteristica.avaliacao == 4
            assert caracteristica.destaque is True
            assert caracteristica.item.grupo_id == grupo_id
        finally:
            db.close()

        invalida = client_admin.post(
            f"/scouting/itens-associados/{caracteristica_id}/guardar",
            data={"avaliacao": "7", "observacao": "Não deve gravar"},
            follow_redirects=True,
        )
        assert "entre 1 e 5" in invalida.text
        db = SessionLocal()
        try:
            assert db.get(ScoutingJogadorItem, caracteristica_id).avaliacao == 4
        finally:
            db.close()

        client_admin.post(
            f"/scouting/itens-associados/{caracteristica_id}/guardar",
            data={"avaliacao": "", "observacao": "Ainda por confirmar"},
            follow_redirects=False,
        )
        db = SessionLocal()
        try:
            assert db.get(ScoutingJogadorItem, caracteristica_id).avaliacao is None
        finally:
            db.close()

        for categoria, titulo, observacao, prioridade in (
            ("tendencia", f"Rejects PnR {sufixo}", "Rejeita para a mão direita.", ""),
            ("game_plan", f"Force Left {sufixo}", "Retirar a mão direita.", "1"),
        ):
            resposta = client_admin.post(
                f"/scouting/jogadores/{jogador_id}/itens",
                data={
                    "categoria": categoria,
                    "nome_novo": titulo,
                    "observacao": observacao,
                    "prioridade": prioridade,
                    "destaque": "true",
                },
                follow_redirects=False,
            )
            assert resposta.status_code == 303

        db = SessionLocal()
        try:
            relacoes = db.query(ScoutingJogadorItem).join(ScoutingItemBiblioteca).filter(
                ScoutingJogadorItem.jogador_id == jogador_id,
                ScoutingItemBiblioteca.categoria.in_(("tendencia", "game_plan")),
            ).all()
            por_categoria = {rel.item.categoria: rel for rel in relacoes}
            tendencia_id = por_categoria["tendencia"].id
            game_plan_id = por_categoria["game_plan"].id
            assert por_categoria["tendencia"].avaliacao is None
            assert por_categoria["game_plan"].prioridade == 1
        finally:
            db.close()

        resposta = client_admin.post(
            f"/scouting/adversarios/{adversario_id}/plano-jogo/{jogo_id}/importar",
            data={"individual_item_ids": str(game_plan_id)},
            follow_redirects=False,
        )
        assert resposta.status_code == 303
        db = SessionLocal()
        try:
            importado = db.query(PlanoJogoItem).join(ItemPlanoJogoBiblioteca).filter(
                ItemPlanoJogoBiblioteca.texto.contains(f"Force Left {sufixo}"),
            ).one()
            assert importado.item.categoria == "chave_defesa"
        finally:
            db.close()

        client_admin.post(
            f"/scouting/itens-associados/{tendencia_id}/eliminar",
            follow_redirects=False,
        )
        db = SessionLocal()
        try:
            assert db.get(ScoutingJogadorItem, tendencia_id) is None
        finally:
            db.close()
    finally:
        _eliminar_adversario_integracao(adversario_id, jogo_id)
        db = SessionLocal()
        try:
            for item in db.query(ScoutingItemBiblioteca).filter(
                ScoutingItemBiblioteca.clube_id == clube_id,
                ScoutingItemBiblioteca.nome.contains(sufixo),
            ).all():
                db.delete(item)
            for item in db.query(ItemPlanoJogoBiblioteca).filter(
                ItemPlanoJogoBiblioteca.clube_id == clube_id,
                ItemPlanoJogoBiblioteca.texto.contains(sufixo),
            ).all():
                db.delete(item)
            grupo = db.get(ScoutingGrupoAvaliacao, grupo_id) if grupo_id else None
            if grupo:
                db.delete(grupo)
            db.commit()
        finally:
            db.close()

def test_scouting_coletivo_separa_todos_os_dados_pedidos():
    modelo = (ROOT / "backend" / "models" / "scouting.py").read_text(encoding="utf-8")
    migracao = (ROOT / "backend" / "migrations" / "versions" / "0048_scouting_coletivo.py").read_text(encoding="utf-8")

    classes = (
        "ScoutingResultadoColetivo", "ScoutingMediaColetiva", "ScoutingEstatisticaColetivaJogo",
        "ScoutingAdversarioItem", "ScoutingLiderEstatistico", "ScoutingOpcoesDefensivas",
        "ScoutingConceitoOfensivo", "ScoutingMomentoPlaybook",
    )
    for classe in classes:
        assert f"class {classe}" in modelo
    for tabela in (
        "scouting_resultados_coletivos", "scouting_estatisticas_coletivas_jogo",
        "scouting_adversarios_itens", "scouting_lideres_estatisticos",
        "scouting_opcoes_defensivas", "scouting_conceitos_ofensivos",
        "scouting_momentos_playbook",
    ):
        assert tabela in migracao


def test_scouting_coletivo_modular_e_transportavel_para_plano_de_jogo():
    modelo = (ROOT / "backend" / "models" / "scouting.py").read_text(encoding="utf-8")
    migracao = (ROOT / "backend" / "migrations" / "versions" / "0057_scouting_coletivo_modular.py").read_text(encoding="utf-8")
    router = (ROOT / "backend" / "routers" / "scouting.py").read_text(encoding="utf-8")
    coletivo = (TEMPLATES_DIR / "scouting" / "coletivo.html").read_text(encoding="utf-8")

    assert "class ScoutingBlocoColetivo" in modelo
    assert 'CheckConstraint("nivel IS NULL OR nivel IN' in modelo
    assert 'CheckConstraint("prioridade IS NULL OR' in modelo
    assert 'op.create_table(\n        "scouting_blocos_coletivos"' in migracao
    assert 'op.add_column("predefinicoes_relatorios"' in migracao
    assert '@router.post("/adversarios/{adversario_id}/coletivo/blocos")' in router
    assert '@router.post("/coletivo/blocos/{bloco_id}/eliminar")' in router
    assert "ScoutingBlocoColetivo.clube_id == adversario.clube_id" in router
    assert "ScoutingBlocoColetivo.clube_id == utilizador.clube_id" in router
    assert 'bloco.tipo in {"resposta", "prioridade_ofensiva"}' in router
    assert "Chaves, perfil e nossa resposta" in coletivo
    assert "Mostrar na leitura fácil" in coletivo


def test_perfil_coletivo_tem_avaliacao_de_zero_a_cinco():
    modelo = (ROOT / "backend" / "models" / "scouting.py").read_text(encoding="utf-8")
    migracao = (ROOT / "backend" / "migrations" / "versions" / "0058_scouting_coletivo_avaliacao.py").read_text(encoding="utf-8")
    perfil = (TEMPLATES_DIR / "scouting" / "_collective_profile.html").read_text(encoding="utf-8")
    router = (ROOT / "backend" / "routers" / "scouting.py").read_text(encoding="utf-8")

    assert "avaliacao >= 0 AND avaliacao <= 5" in modelo
    assert 'op.add_column("scouting_blocos_coletivos"' in migracao
    assert "range(0, 6)" in perfil
    assert 'name="avaliacao"' in perfil
    assert "Perfil coletivo 0–5" in perfil
    assert "0 <= avaliacao <= 5" in router


def test_pagina_coletiva_tem_estatistica_leitura_e_playbook_completos():
    coletivo = (TEMPLATES_DIR / "scouting" / "coletivo.html").read_text(encoding="utf-8")
    cartao = (TEMPLATES_DIR / "scouting" / "_drawn_card.html").read_text(encoding="utf-8")
    router = (ROOT / "backend" / "routers" / "scouting.py").read_text(encoding="utf-8")

    for titulo in (
        "Últimos 5 resultados", "Média estatística da equipa", "Características estatísticas",
        "Líderes estatísticos", "Identidade ofensiva e defensiva", "Principais conceitos ofensivos",
        "Principais opções defensivas", "Playbook coletivo",
    ):
        assert titulo in coletivo
    assert 'data-library-search' in coletivo
    assert 'data-defense-toggle' in coletivo
    assert '/playbook/studio/setplays/' in cartao
    assert '/mover/cima' in cartao and '/mover/baixo' in cartao
    assert "loop.index" not in cartao
    assert "elemento.ordem" in cartao
    assert "_media_calculada" in router
    assert 'origem="scouting"' in router
    assert "_garantir_configuracao_coletiva" in router
    assert "except IntegrityError" in router
    assert "adversario.media_coletiva" not in coletivo
    assert "adversario.opcoes_defensivas" not in coletivo


def test_ficha_individual_nao_renderiza_associacoes_orfas_diretamente():
    individual = (TEMPLATES_DIR / "scouting" / "individual.html").read_text(encoding="utf-8")
    inteligencia = (TEMPLATES_DIR / "scouting" / "_individual_intelligence.html").read_text(encoding="utf-8")

    assert "itens_por_categoria.get(categoria, [])" in inteligencia
    assert "jogador.itens" not in individual


def test_playbook_studio_regressa_ao_scouting_coletivo():
    router = (ROOT / "backend" / "routers" / "playbook.py").read_text(encoding="utf-8")
    studio = (TEMPLATES_DIR / "playbook" / "detalhe.html").read_text(encoding="utf-8")

    assert "ScoutingConceitoOfensivo" in router
    assert "ScoutingMomentoPlaybook" in router
    assert "url_voltar" in router
    assert "url_voltar|default" in studio


def test_scouting_coletivo_guarda_cinco_inicial_e_rotacoes_previstas():
    modelo = (ROOT / "backend" / "models" / "scouting.py").read_text(encoding="utf-8")
    migracao = (ROOT / "backend" / "migrations" / "versions" / "0049_scouting_rotacao_prevista.py").read_text(encoding="utf-8")
    coletivo = (TEMPLATES_DIR / "scouting" / "coletivo.html").read_text(encoding="utf-8")
    router = (ROOT / "backend" / "routers" / "scouting.py").read_text(encoding="utf-8")

    assert "class ScoutingRotacaoPrevista" in modelo
    assert "scouting_rotacoes_previstas" in migracao
    assert "Cinco inicial e principais rotações" in coletivo
    assert 'name="titular_{{ indice + 1 }}"' in coletivo
    assert 'name="rotacoes"' in coletivo
    assert "guardar_rotacao_prevista" in router


def test_scouting_coletivo_guarda_ideia_chave_sem_refresh_e_exporta_no_cabecalho():
    coletivo = (TEMPLATES_DIR / "scouting" / "coletivo.html").read_text(encoding="utf-8")
    cabecalho = (TEMPLATES_DIR / "relatorios" / "_scouting_cabecalho.html").read_text(encoding="utf-8")
    router = (ROOT / "backend" / "routers" / "scouting.py").read_text(encoding="utf-8")

    assert 'id="resumo-equipa"' in coletivo
    assert 'name="observacoes"' in coletivo
    assert 'data-studio-async' in coletivo
    assert 'data-studio-refresh="collective-summary"' in coletivo
    assert '@router.post("/adversarios/{adversario_id}/coletivo/resumo")' in router
    assert "adversario.observacoes = _limpo" in router
    assert "resumo=none" in cabecalho
    assert "resumo|truncate(220)" in cabecalho


def test_plano_de_jogo_vive_no_dossier_e_importa_scouting_sem_substituir():
    tabs = (TEMPLATES_DIR / "scouting" / "_departamento_tabs.html").read_text(encoding="utf-8")
    plano = (TEMPLATES_DIR / "scouting" / "plano_jogo.html").read_text(encoding="utf-8")
    biblioteca = (TEMPLATES_DIR / "jogos" / "_plano_biblioteca.html").read_text(encoding="utf-8")
    router = (ROOT / "backend" / "routers" / "scouting.py").read_text(encoding="utf-8")
    jogos = (ROOT / "backend" / "routers" / "jogos.py").read_text(encoding="utf-8")

    assert "('plano-jogo','Plano de Jogo')" in tabs
    assert "Importar análise do Scouting Coletivo" in plano
    assert "sem substituir decisões já tomadas" in plano
    assert 'action="/jogos/{{ jogo.id }}/plano"' in plano
    assert "_preencher_se_vazio" in router
    assert "importar_scouting_para_plano" in router
    assert 'voltar.startswith("/scouting/")' in jogos
    assert 'name="rotacao_{{ grupo }}_{{ posicao }}"' in plano
    assert "Selecionar jogada da equipa" in biblioteca
    assert "Criar e guardar uma nova opção" in biblioteca


def test_scouting_atualiza_acoes_locais_sem_refresh_da_pagina():
    studio = (ROOT / "frontend" / "static" / "js" / "scouting-studio.js").read_text(encoding="utf-8")
    individual = (TEMPLATES_DIR / "scouting" / "individual.html").read_text(encoding="utf-8")
    coletivo = (TEMPLATES_DIR / "scouting" / "coletivo.html").read_text(encoding="utf-8")
    roster = (TEMPLATES_DIR / "scouting" / "roster.html").read_text(encoding="utf-8")
    itens = (TEMPLATES_DIR / "scouting" / "_collective_items.html").read_text(encoding="utf-8")

    assert 'form[data-studio-async]' in studio
    assert 'fetch(action' in studio
    assert 'submitter.getAttribute("formaction")' in studio
    assert 'submitter.getAttribute("formmethod")' in studio
    assert "submitter.formAction" not in studio
    assert 'window.location.reload' not in studio
    inteligencia = (TEMPLATES_DIR / "scouting" / "_individual_intelligence.html").read_text(encoding="utf-8")
    assert 'data-studio-region="individual-profile"' in inteligencia
    assert 'data-studio-refresh="individual-profile"' in inteligencia
    assert 'data-studio-region="collective-items-{{ categoria_atual }}"' in itens
    assert 'data-studio-refresh="collective-items-{{ categoria }}"' in coletivo
    assert 'data-studio-region="roster-list"' in roster
    assert 'data-studio-refresh="roster-list"' in roster
    plano = (TEMPLATES_DIR / "scouting" / "plano_jogo.html").read_text(encoding="utf-8")
    assert 'data-studio-region="game-plan"' in plano
    assert plano.count('data-studio-refresh="game-plan"') >= 2

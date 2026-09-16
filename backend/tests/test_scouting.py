from pathlib import Path

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
    assert "Biblioteca reutilizável" in individual
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
    assert "_media_calculada" in router
    assert 'origem="scouting"' in router


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


def test_plano_de_jogo_vive_no_dossier_e_importa_scouting_sem_substituir():
    tabs = (TEMPLATES_DIR / "scouting" / "_departamento_tabs.html").read_text(encoding="utf-8")
    plano = (TEMPLATES_DIR / "scouting" / "plano_jogo.html").read_text(encoding="utf-8")
    router = (ROOT / "backend" / "routers" / "scouting.py").read_text(encoding="utf-8")
    jogos = (ROOT / "backend" / "routers" / "jogos.py").read_text(encoding="utf-8")

    assert "('plano-jogo','Plano de Jogo')" in tabs
    assert "Importar análise do Scouting Coletivo" in plano
    assert "O conteúdo escrito no plano nunca é substituído" in plano
    assert 'action="/jogos/{{ jogo.id }}/plano"' in plano
    assert "_preencher_se_vazio" in router
    assert "importar_scouting_para_plano" in router
    assert 'voltar.startswith("/scouting/")' in jogos

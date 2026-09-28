from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / "frontend" / "templates"
VISUAL_REFRESH = ROOT / "frontend" / "static" / "css" / "visual-refresh.css"


def test_aplicacao_carrega_revisao_visual_sem_remover_estilos_existentes():
    base = (TEMPLATES / "base.html").read_text(encoding="utf-8")
    login = (TEMPLATES / "login.html").read_text(encoding="utf-8")

    assert "/static/css/design-system.css" in base
    assert "/static/css/visual-refresh.css" in base
    assert "/static/css/visual-refresh.css" in login
    assert 'class="login-experience' in login
    assert "{% block conteudo %}" in base


def test_revisao_visual_cobre_shell_componentes_e_responsividade():
    css = VISUAL_REFRESH.read_text(encoding="utf-8")

    for selector in (
        "#app-sidebar",
        ".ds-page-header",
        ".ds-panel",
        ".ds-kpi",
        ".ds-button-primary",
        "#conteudo-principal table",
        "dialog::backdrop",
        "body.login-experience",
    ):
        assert selector in css

    assert "@media (max-width:640px)" in css
    assert "@media (prefers-reduced-motion:reduce)" in css
    assert "@media print" in css
    assert "--vr-electric" in css
    assert "linear-gradient(120deg,#0b1424" in css


def test_fundo_decorativo_nao_deixa_faixa_da_marca_ao_recolher_sidebar():
    css = VISUAL_REFRESH.read_text(encoding="utf-8")

    assert "body.sidebar-hidden #conteudo-principal::before" in css
    assert "body.sidebar-hidden {" in css
    assert "inset:0 0 auto 0" in css
    assert "background:linear-gradient(180deg,#f8fbff,transparent)" in css


def test_documentos_partilham_identidade_e_regras_de_paginacao():
    branding = (TEMPLATES / "partials" / "pdf_branding.html").read_text(encoding="utf-8")
    documento = (TEMPLATES / "relatorios" / "_documento.html").read_text(encoding="utf-8")
    facil = (TEMPLATES / "relatorios" / "_facil_estilos.html").read_text(encoding="utf-8")
    scouting = (TEMPLATES / "relatorios" / "_scouting_estilos.html").read_text(encoding="utf-8")

    assert "--pdf-primary" in branding
    assert "linear-gradient(125deg, var(--pdf-primary-dark), var(--pdf-primary))" in branding
    assert "@bottom-right" in branding
    assert "counter(pages)" in branding
    assert "Performance intelligence / documento oficial" in branding
    assert "pdf-brand-signal" in branding
    assert "page-break-inside: avoid" in branding
    assert "thead { display: table-header-group; }" in branding
    assert "var(--pdf-line)" in documento
    assert "var(--pdf-surface)" in facil
    assert "var(--pdf-primary)" in scouting
    assert "var(--pdf-on-primary)" in scouting
    assert "page-break-inside:avoid" in scouting


def test_cartao_individual_inovador_preserva_uma_pagina_por_atleta():
    cartao = (TEMPLATES / "relatorios" / "scouting_individual_facil.html").read_text(encoding="utf-8")

    assert "INTELIGÊNCIA DE JOGO / LEITURA RÁPIDA" not in cartao
    assert "identidade.logo_principal" in cartao
    assert "identidade.nome_oficial" in cartao
    assert "j.ficha.resumo" in cartao
    assert ".player-sheet:last-child{page-break-after:auto}" in cartao
    assert ".player-sheet::after" not in cartao
    assert "player-hotzone" in cartao


def test_exportacoes_reais_usam_a_identidade_pdf_partilhada():
    documentos = set(TEMPLATES.rglob("*pdf*.html")) | set(TEMPLATES.rglob("*print*.html"))
    documentos = {ficheiro for ficheiro in documentos if "partials" not in ficheiro.parts}

    sem_identidade = []
    for ficheiro in documentos:
        conteudo = ficheiro.read_text(encoding="utf-8")
        if "estilo_pdf()" not in conteudo:
            sem_identidade.append(ficheiro.relative_to(TEMPLATES).as_posix())

    assert len(documentos) >= 30
    assert sem_identidade == []


def test_calendarios_pdf_usam_a_cor_dominante_do_clube():
    calendarios = (
        TEMPLATES / "calendario_pdf.html",
        TEMPLATES / "calendario_partilhavel_pdf.html",
        TEMPLATES / "mesociclo_partilhavel_pdf.html",
        TEMPLATES / "planeamento_clube" / "anual_calendario_pdf.html",
    )

    for calendario in calendarios:
        conteudo = calendario.read_text(encoding="utf-8")
        assert "var(--pdf-primary)" in conteudo
        assert "var(--pdf-on-primary)" in conteudo
        assert "--club-primary" not in conteudo

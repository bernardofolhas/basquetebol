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


def test_documentos_partilham_identidade_e_regras_de_paginacao():
    branding = (TEMPLATES / "partials" / "pdf_branding.html").read_text(encoding="utf-8")
    documento = (TEMPLATES / "relatorios" / "_documento.html").read_text(encoding="utf-8")
    facil = (TEMPLATES / "relatorios" / "_facil_estilos.html").read_text(encoding="utf-8")
    scouting = (TEMPLATES / "relatorios" / "_scouting_estilos.html").read_text(encoding="utf-8")

    assert "--pdf-night" in branding
    assert "linear-gradient(125deg, var(--pdf-night)" in branding
    assert "page-break-inside: avoid" in branding
    assert "thead { display: table-header-group; }" in branding
    assert "var(--pdf-line)" in documento
    assert "var(--pdf-surface)" in facil
    assert "var(--pdf-night)" in scouting
    assert "page-break-inside:avoid" in scouting

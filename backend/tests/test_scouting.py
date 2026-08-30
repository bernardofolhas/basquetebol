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
    navbar = (TEMPLATES_DIR / "partials" / "navbar_global.html").read_text(
        encoding="utf-8"
    )
    detalhe_jogo = (TEMPLATES_DIR / "jogos" / "detalhe.html").read_text(
        encoding="utf-8"
    )

    assert 'Plano de jogo' in navbar
    assert "'/jogos/' ~ jogo_nav.id ~ '/plano'" in navbar
    assert "'/scouting/jogos/' ~ jogo_nav.id" in navbar
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

from pathlib import Path

from paths import TEMPLATES_DIR
from template_config import Jinja2Templates


ROOT = Path(__file__).resolve().parents[2]
CSS = ROOT / "frontend" / "static" / "css" / "design-system.css"


def test_todos_os_templates_continuam_validos():
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    ficheiros = list(TEMPLATES_DIR.rglob("*.html"))

    for ficheiro in ficheiros:
        nome = ficheiro.relative_to(TEMPLATES_DIR).as_posix()
        templates.env.get_template(nome)

    assert len(ficheiros) >= 120


def test_sistema_visual_tem_componentes_e_estados_comuns():
    conteudo = CSS.read_text(encoding="utf-8")

    for componente in (
        ".ds-button-primary",
        ".ds-button-danger",
        ".ds-empty",
        ".ds-flash",
        ".ds-status-draft",
        ".ds-status-pending",
        ".ds-status-confirmed",
        ".ds-status-executed",
        ".ds-status-conflict",
    ):
        assert componente in conteudo


def test_base_preserva_navegacao_acessivel_e_responsiva():
    conteudo = (TEMPLATES_DIR / "base.html").read_text(encoding="utf-8")

    assert 'href="#conteudo-principal"' in conteudo
    assert 'aria-live="polite"' in conteudo
    assert 'wrapper.classList.add("ds-table-scroll")' in conteudo
    assert 'id="menu-mobile"' in (TEMPLATES_DIR / "partials" / "navbar_global.html").read_text(encoding="utf-8")


def test_login_mantem_recuperacao_e_melhora_utilizacao():
    conteudo = (TEMPLATES_DIR / "login.html").read_text(encoding="utf-8")

    assert 'action="/login-form"' in conteudo
    assert 'href="/recuperar-password"' in conteudo
    assert 'id="mostrar-password"' in conteudo
    assert 'autocomplete="current-password"' in conteudo

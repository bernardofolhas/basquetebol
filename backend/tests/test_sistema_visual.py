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


def test_acoes_legadas_herdam_o_sistema_visual_do_clube():
    conteudo = CSS.read_text(encoding="utf-8")

    assert "Compatibility layer for legacy action controls" in conteudo
    assert 'background:var(--clube-primary) !important;' in conteudo
    assert '#conteudo-principal :is(a, button, input[type="submit"])[class*="bg-red-"]' in conteudo
    assert "outline:3px solid color-mix" in conteudo


def test_base_preserva_navegacao_acessivel_e_responsiva():
    conteudo = (TEMPLATES_DIR / "base.html").read_text(encoding="utf-8")

    assert 'href="#conteudo-principal"' in conteudo
    assert 'aria-live="polite"' in conteudo
    assert 'wrapper.classList.add("ds-table-scroll")' in conteudo
    assert 'id="menu-mobile"' in (TEMPLATES_DIR / "partials" / "navbar_global.html").read_text(encoding="utf-8")
    assert ".ds-team-direct-nav { display:grid;grid-template-columns:repeat(2" in CSS.read_text(encoding="utf-8")


def test_navegacao_interna_nao_abre_novas_abas():
    templates = list(TEMPLATES_DIR.rglob("*.html"))

    for template in templates:
        conteudo = template.read_text(encoding="utf-8")
        assert 'target="_blank"' not in conteudo, template

    base = (TEMPLATES_DIR / "base.html").read_text(encoding="utf-8")
    assert 'element.removeAttribute("target")' in base


def test_shell_profissional_agrupa_acoes_e_completa_o_perfil():
    estilos = CSS.read_text(encoding="utf-8")
    contexto = (TEMPLATES_DIR / "partials" / "equipa_contexto.html").read_text(encoding="utf-8")
    navegacao = (TEMPLATES_DIR / "partials" / "navbar_global.html").read_text(encoding="utf-8")

    assert 'class="ds-menu ds-page-actions"' in contexto
    assert "Ações da página" in contexto
    assert 'class="ds-user-summary"' in navegacao
    assert "{{ utilizador.nome }}" in navegacao
    assert ".ds-page-actions-menu" in estilos
    assert ".ds-team-context:has(.ds-page-actions[open])" in estilos
    assert ".ds-page-actions[open]" in estilos
    assert ".ds-user-menu-trigger" in estilos
    assert "ds-user-menu-dropdown" in navegacao
    assert 'name="csrf_token" value="{{ request.session.get(\'_csrf\', \'\') }}"' in navegacao
    assert ".ds-user-menu-dropdown" in estilos


def test_shell_autenticado_renderiza_header_completo(client_admin):
    resposta = client_admin.get("/dashboard")

    assert resposta.status_code == 200
    assert 'id="header-navigation"' in resposta.text
    assert 'aria-label="Caixa de entrada"' in resposta.text
    assert 'class="ds-user-summary"' in resposta.text
    assert "Ações rápidas" in resposta.text


def test_planeamentos_longos_usam_abas_internas_sem_alterar_exportacoes():
    base = (TEMPLATES_DIR / "base.html").read_text(encoding="utf-8")
    css = CSS.read_text(encoding="utf-8")
    detalhes = {
        "anuais/detalhe.html": ("anual", "calendario", "macrociclos", "objetivos", "estado"),
        "macrociclos/detalhe.html": ("macro", "calendario", "mesociclos", "objetivos"),
        "mesociclos/detalhe.html": ("meso", "calendario", "microciclos", "objetivos", "reflexao"),
        "microciclos/detalhe.html": ("micro", "agenda", "conteudos", "carga", "objetivos", "reflexao"),
    }

    assert "[data-workspace-tabs]" in base
    assert "window.sessionStorage.setItem(storageKey,name)" in base
    assert ".ds-workspace-tabs" in css
    assert "[data-workspace-panel][hidden]" in css

    for caminho, (grupo, *abas) in detalhes.items():
        conteudo = (TEMPLATES_DIR / "planeamento" / caminho).read_text(encoding="utf-8")
        assert f'data-workspace-tabs="{grupo}"' in conteudo
        for aba in abas:
            assert f'data-workspace-tab="{aba}"' in conteudo
            assert f'data-workspace-panel="{grupo}:{aba}"' in conteudo


def test_paginas_operacionais_longas_usam_o_mesmo_padrao_de_abas():
    detalhes = {
        "equipas/detalhe.html": ("equipa", "atividade", "equipa", "logistica"),
        "jogos/detalhe.html": ("jogo", "resultado", "convocatoria"),
        "jogadores/detalhe.html": ("jogador", "resumo", "perfil", "evolucao", "processo"),
        "treino/plano.html": ("treino", "dados", "exercicios", "reflexao", "resumo"),
    }

    for caminho, (grupo, *abas) in detalhes.items():
        conteudo = (TEMPLATES_DIR / caminho).read_text(encoding="utf-8")
        assert f'data-workspace-tabs="{grupo}"' in conteudo
        for aba in abas:
            assert f'data-workspace-tab="{aba}"' in conteudo
            assert f'data-workspace-panel="{grupo}:{aba}"' in conteudo


def test_microciclo_adiciona_conteudos_individualmente_em_cada_celula():
    conteudo = (
        TEMPLATES_DIR / "planeamento" / "microciclos" / "detalhe.html"
    ).read_text(encoding="utf-8")

    assert "Gerir conteúdos" not in conteudo
    assert 'id="conteudo-dialog"' in conteudo
    assert "abrirConteudoDialog({{ treino.sessao_id }}" in conteudo
    assert "data-editar-conteudo" in conteudo
    assert "data-minutos-balanco" in conteudo
    assert "Use o sinal + de cada célula" in conteudo


def test_microciclo_guarda_cargas_e_reflexao_sem_navegar():
    conteudo = (
        TEMPLATES_DIR / "planeamento" / "microciclos" / "detalhe.html"
    ).read_text(encoding="utf-8")

    assert 'id="guardar-cargas"' in conteudo
    assert "event.preventDefault();" in conteudo
    assert "X-Requested-With" in conteudo
    assert 'id="reflexao-form"' in conteudo


def test_equipa_abre_explicitamente_no_resumo_e_base_usa_logo_como_icone():
    dashboard = (TEMPLATES_DIR / "dashboard_treinador.html").read_text(encoding="utf-8")
    base = (TEMPLATES_DIR / "base.html").read_text(encoding="utf-8")

    assert '/equipas/{{ item.equipa.id }}/resumo' in dashboard
    assert '<link rel="icon" href="{{ identidade.logo_principal }}">' in base
    assert '/static/img/favicon-plataforma.svg' in base
    assert "scrollbar-gutter:auto" in (
        TEMPLATES_DIR.parent / "static" / "css" / "design-system.css"
    ).read_text(encoding="utf-8")


def test_login_mantem_recuperacao_e_melhora_utilizacao():
    conteudo = (TEMPLATES_DIR / "login.html").read_text(encoding="utf-8")

    assert 'action="/login-form"' in conteudo
    assert 'href="/recuperar-password"' in conteudo
    assert 'id="mostrar-password"' in conteudo
    assert 'autocomplete="current-password"' in conteudo
    assert '/static/img/favicon-plataforma.svg' in conteudo
    assert 'identidade.logo_principal' not in conteudo

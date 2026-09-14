from pathlib import Path
from types import SimpleNamespace

import pytest
from jinja2 import Environment, FileSystemLoader


@pytest.mark.parametrize('perfil', ['administrador', 'coordenador', 'treinador', 'staff'])
def test_sidebar_nao_enumera_registos_mas_preserva_caixa_de_entrada(perfil):
    templates = Path(__file__).resolve().parents[2] / 'frontend' / 'templates'
    env = Environment(loader=FileSystemLoader(templates), autoescape=True)
    env.filters['data_pt'] = str
    nav = {
        'equipas': [{'id': 7, 'nome': 'Sub-18'}],
        'jogos_proximos': [{'id': 42, 'equipa_id': 7, 'adversario': 'Adversario teste'}],
        'total_pendencias': 1,
        'total_notificacoes': 1,
        'pendencias': [{'label': 'Grupo teste', 'itens': [{
            'link': '/jogos/42/plano', 'titulo': 'Pendencia teste', 'urgente': False,
            'item': {'equipa_nome': 'Sub-18'},
        }]}],
        'notificacoes': [{'id': 9, 'titulo': 'Aviso teste', 'mensagem': 'Mensagem', 'lida': False}],
    }
    html = env.get_template('partials/navbar_global.html').render(
        request=SimpleNamespace(state=SimpleNamespace(navegacao=nav), session={}),
        perfil=perfil, p='/treino/sessoes/5', modo_plataforma=False,
        identidade={'nome_curto': 'Clube'}, equipa_contexto_id=7,
        equipa_contexto_nome='Sub-18', utilizador={'nome': 'Utilizador teste'},
    )
    sidebar = html.split('<aside', 1)[1].split('</aside>', 1)[0]
    assert '/jogos/42/plano' not in sidebar
    assert '/scouting/jogos/42' not in sidebar
    assert 'Pendencia teste' not in sidebar
    assert 'Aviso teste' not in sidebar
    assert 'data-inbox-open' in sidebar
    assert '/jogos/equipas/7' in sidebar
    assert '/logout' in sidebar
    dialog = html.split('<dialog', 1)[1].split('</dialog>', 1)[0]
    assert 'Pendencia teste' in dialog
    assert '/notificacoes/9/ler' in dialog
    assert '/notificacoes/ler-todas' in dialog
    assert '/notificacoes/limpar-lidas' in dialog


def test_sidebar_sem_equipa_da_acesso_direto_a_planeamento_e_analise():
    templates = Path(__file__).resolve().parents[2] / 'frontend' / 'templates'
    env = Environment(loader=FileSystemLoader(templates), autoescape=True)
    env.filters['data_pt'] = str
    html = env.get_template('partials/navbar_global.html').render(
        request=SimpleNamespace(state=SimpleNamespace(navegacao={
            'equipas': [{'id': 7, 'nome': 'Sub-18'}],
        }), session={}),
        perfil='treinador', p='/dashboard', modo_plataforma=False,
        identidade={'nome_curto': 'Clube'}, equipa_contexto_id=None,
        equipa_contexto_nome=None, utilizador={'nome': 'Treinador'},
    )
    assert '/planeamento/equipas/7/anuais' in html
    assert '/analise/equipas/7' in html
    assert 'Ações rápidas' not in html
    assert 'Escolhe a equipa que queres analisar.' in html


def test_sidebar_usa_seccoes_recolhiveis_com_estado_persistente():
    raiz = Path(__file__).resolve().parents[2]
    navbar = (raiz / 'frontend' / 'templates' / 'partials' / 'navbar_global.html').read_text(encoding='utf-8')
    javascript = (raiz / 'frontend' / 'static' / 'js' / 'sidebar.js').read_text(encoding='utf-8')
    estilos = (raiz / 'frontend' / 'static' / 'css' / 'sidebar.css').read_text(encoding='utf-8')

    for seccao in ('equipa', 'planeamento', 'acao', 'analise', 'gestao', 'acoes-rapidas'):
        assert f'data-sidebar-section="{seccao}"' in navbar
    assert navbar.count('class="sidebar-section-chevron"') >= 6
    assert "localStorage.getItem('sidebar-open-section')" in javascript
    assert "if (other !== group) other.open = false" in javascript
    assert "candidates[0].link.closest('details[data-sidebar-section]')" in javascript
    assert '.sidebar-group[open]>.sidebar-heading .sidebar-section-chevron' in estilos

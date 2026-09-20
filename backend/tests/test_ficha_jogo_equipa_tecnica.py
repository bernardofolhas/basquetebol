from datetime import date
from pathlib import Path
from types import SimpleNamespace
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from routers.equipas import FUNCOES_EQUIPE_TECNICA, _agrupar_equipa_tecnica
from routers.jogos import _jogadores_ficha
from routers.admin import _funcao_tecnica
from models.utilizador import PerfilEnum


def test_equipa_tecnica_agrupa_apenas_funcoes_com_elementos():
    elementos = [
        SimpleNamespace(id=2, nome="Fisioterapeuta", funcao="Fisioterapeuta"),
        SimpleNamespace(id=1, nome="Treinador", funcao="Treinador"),
    ]

    grupos = _agrupar_equipa_tecnica(elementos)

    assert [funcao for funcao, _ in grupos] == ["Treinador", "Fisioterapeuta"]
    assert all(funcao in FUNCOES_EQUIPE_TECNICA for funcao, _ in grupos)


def test_perfis_tecnicos_usam_funcoes_da_equipa_sem_criar_novos_logins():
    assert _funcao_tecnica(PerfilEnum.fisioterapeuta, "Médico") == "Fisioterapeuta"
    assert _funcao_tecnica(PerfilEnum.staff, "Médico") == "Médico"
    assert _funcao_tecnica(PerfilEnum.staff, "") == "Seccionista"


def test_ficha_jogo_usa_a_ultima_altura_sem_gravar_no_perfil():
    jogador = SimpleNamespace(
        registos_antropometricos=[
            SimpleNamespace(data=date(2026, 1, 2), altura=181),
            SimpleNamespace(data=date(2026, 3, 4), altura=184),
        ]
    )

    resultado = _jogadores_ficha([jogador])

    assert resultado == [jogador]
    assert jogador.altura_ficha == 184


def test_ficha_jogo_e_campos_federativos_estao_disponiveis_no_fluxo():
    raiz = Path(__file__).resolve().parents[2]
    formulario = (raiz / "frontend/templates/jogos/ficha_jogo.html").read_text(encoding="utf-8")
    pdf = (raiz / "frontend/templates/jogos/ficha_jogo_pdf.html").read_text(encoding="utf-8")
    jogador = (raiz / "frontend/templates/jogadores/form.html").read_text(encoding="utf-8")
    tecnico = (raiz / "frontend/templates/treinadores/form.html").read_text(encoding="utf-8")

    assert 'action="/jogos/{{ jogo.id }}/ficha-jogo/pdf"' in formulario
    assert 'name="jogadores_ids"' in formulario
    assert 'name="elementos_ids"' in formulario
    assert 'name="capitao_id"' in formulario
    assert 'name="cor_equipamento"' in formulario
    assert "Nº Licença FPB" in pdf
    assert 'name="numero_licenca_fpb"' in jogador
    assert 'name="funcao"' in tecnico


def test_sistema_de_camadas_nao_altera_o_layout_de_roles_sem_menu():
    raiz = Path(__file__).resolve().parents[2]
    css = (raiz / "frontend/static/css/design-system.css").read_text(encoding="utf-8")

    assert "--layer-popover" in css
    assert ":where([role=\"menu\"],[role=\"listbox\"]) { z-index:var(--layer-popover); }" in css
    assert '[role="menu"],[role="listbox"],[data-floating-ui-portal]) {' not in css

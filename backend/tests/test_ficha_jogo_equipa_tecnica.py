from base64 import b64encode
from datetime import date
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
import sys

from PIL import Image
from pypdf import PdfReader
from weasyprint import HTML

sys.path.append(str(Path(__file__).resolve().parents[1]))

from routers.equipas import FUNCOES_EQUIPE_TECNICA, _agrupar_equipa_tecnica
from routers.jogos import _fotografias_ficha, _jogadores_ficha, _ordem_staff_ficha
from routers.admin import _funcao_tecnica
from routers.treinadores import _perfil_login_para_funcao
from models.utilizador import PerfilEnum
from paths import TEMPLATES_DIR
from template_config import Jinja2Templates


def test_equipa_tecnica_agrupa_apenas_funcoes_com_elementos():
    elementos = [
        SimpleNamespace(id=2, nome="Fisioterapeuta", funcao="Fisioterapeuta"),
        SimpleNamespace(id=1, nome="Treinador", funcao="Treinador"),
    ]

    grupos = _agrupar_equipa_tecnica(elementos)

    assert [titulo for titulo, _ in grupos] == ["Treinador principal", "Fisioterapeutas"]
    assert [elemento.id for _, elementos_grupo in grupos for elemento in elementos_grupo] == [1, 2]


def test_equipa_tecnica_mostra_todos_os_cargos_na_ordem_pedida():
    funcoes = (
        "Médico", "Team Manager", "Treinador Adjunto", "Treinador", "Scout",
        "Adjunto", "Treinador Principal", "Fisioterapeuta",
    )
    elementos = [SimpleNamespace(id=numero, nome=f"Pessoa {numero}", funcao=funcao) for numero, funcao in enumerate(funcoes, 1)]

    grupos = _agrupar_equipa_tecnica(elementos)

    assert [titulo for titulo, _ in grupos] == [
        "Treinador principal", "Treinadores adjuntos", "Team managers",
        "Fisioterapeutas", "Médicos", "Scout",
    ]
    assert [[item.funcao for item in grupo] for _, grupo in grupos[:3]] == [
        ["Treinador", "Treinador Principal"],
        ["Treinador Adjunto", "Adjunto"],
        ["Team Manager"],
    ]
    assert sum(len(grupo) for _, grupo in grupos) == len(elementos)


def test_perfis_tecnicos_usam_funcoes_da_equipa_sem_criar_novos_logins():
    assert _funcao_tecnica(PerfilEnum.fisioterapeuta, "Médico") == "Fisioterapeuta"
    assert _funcao_tecnica(PerfilEnum.secretaria, "") == "Secretaria"
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


def test_ficha_jogo_prioriza_funcoes_do_staff_e_permite_cadastra_las():
    funcoes = ["Médico", "Team manager", "Adjunto", "Treinador", "Treinador Principal", "Fisioterapeuta"]
    elementos = [SimpleNamespace(nome=funcao, funcao=funcao) for funcao in funcoes]

    assert [item.funcao for item in sorted(elementos, key=_ordem_staff_ficha)] == [
        "Treinador Principal", "Treinador", "Adjunto", "Team manager", "Fisioterapeuta", "Médico",
    ]
    assert all(funcao in FUNCOES_EQUIPE_TECNICA for funcao in funcoes)
    assert _perfil_login_para_funcao("Treinador Principal") == PerfilEnum.treinador
    assert _perfil_login_para_funcao("Adjunto") == PerfilEnum.treinador


def test_ficha_jogo_embebe_foto_e_reserva_espaco_quando_nao_existe(monkeypatch):
    imagem = BytesIO()
    Image.new("RGB", (40, 40), "red").save(imagem, format="PNG")
    uri = "data:image/png;base64," + b64encode(imagem.getvalue()).decode("ascii")
    foto = SimpleNamespace(suffix=".png", is_file=lambda: True)
    monkeypatch.setattr("routers.jogos.caminho_fotografia", lambda url: foto if url else None)
    monkeypatch.setattr("routers.jogos.imagem_estatica_data_uri", lambda caminho, mime: uri)
    jogadores = [
        SimpleNamespace(
            id=numero, nome=f"Atleta {numero}", fotografia="/static/uploads/jogadores/atleta.png" if numero == 1 else None,
            numero_licenca_fpb=str(numero), numero_camisola=numero, altura_ficha=180, posicao="Base",
        )
        for numero in range(1, 13)
    ]
    fotografias = _fotografias_ficha(jogadores)
    jogo = SimpleNamespace(
        equipa=SimpleNamespace(nome="CB Queluz"), adversario="Rivals BC", numero_jogo="123",
        competicao="Liga", data=date(2026, 10, 5), hora="15:00",
    )
    elementos = [
        SimpleNamespace(nome=funcao, funcao=funcao, numero_fpb=str(numero))
        for numero, funcao in enumerate(("Treinador Principal", "Adjunto", "Team manager", "Fisioterapeuta"), 1)
    ]
    html = Jinja2Templates(directory=str(TEMPLATES_DIR)).get_template("jogos/ficha_jogo_pdf.html").render(
        jogo=jogo, jogadores=jogadores, fotografias=fotografias, elementos_tecnicos=elementos,
        capitao_id=1, cor_equipamento="Branco", data_exportacao="05/10/2026", identidade={},
    )

    assert 'src="data:image/png;base64,' in html
    assert html.count('class="foto-ausente"') == 11
    pdf = HTML(string=html).write_pdf()
    paginas = PdfReader(BytesIO(pdf)).pages
    assert len(paginas) == 1, [pagina.extract_text()[-400:] for pagina in paginas]


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

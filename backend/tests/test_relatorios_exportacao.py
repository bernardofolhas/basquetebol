from pathlib import Path

from starlette.datastructures import FormData

from models.utilizador import PerfilEnum
from routers.exportacoes import RELATORIOS_CONFIG, _configuracao_relatorio, _secoes_padrao


ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / "frontend" / "templates"


class UtilizadorFalso:
    def __init__(self, perfil):
        self.perfil = perfil


def test_quatro_tipos_e_tres_formatos_tem_template_proprio():
    assert set(RELATORIOS_CONFIG) == {"roster", "scouting-individual", "scouting-coletivo", "plano-jogo"}
    for tipo in RELATORIOS_CONFIG:
        base = tipo.replace("-", "_")
        for formato in ("completo", "facil", "a3"):
            assert (TEMPLATES / "relatorios" / f"{base}_{formato}.html").is_file()


def test_a3_usa_tamanho_fisico_a3_e_composicao_propria():
    documento = (TEMPLATES / "relatorios" / "_documento.html").read_text(encoding="utf-8")
    assert "A3" in documento
    assert "size:" in documento
    assert "formato == 'a3'" in documento


def test_contactos_sao_removidos_para_perfil_nao_autorizado():
    dados = FormData([
        ("formato", "completo"),
        ("orientacao", "retrato"),
        ("secoes", "identificacao"),
        ("secoes", "contactos"),
        ("ordem", "contactos,identificacao"),
    ])
    _, _, secoes = _configuracao_relatorio("roster", dados, UtilizadorFalso(PerfilEnum.treinador))
    assert secoes == ["fotografia", "identificacao"]


def test_a3_nunca_inclui_contactos_mesmo_para_administrador():
    dados = FormData([
        ("formato", "a3"),
        ("secoes", "contactos"),
        ("secoes", "identificacao"),
        ("ordem", "contactos,identificacao"),
    ])
    formato, _, secoes = _configuracao_relatorio("roster", dados, UtilizadorFalso(PerfilEnum.administrador))
    assert formato == "a3"
    assert secoes == ["fotografia", "identificacao"]


def test_ordem_escolhida_e_preservada_e_vazios_usam_padrao():
    dados = FormData([
        ("formato", "facil"),
        ("secoes", "zonas"),
        ("secoes", "identificacao"),
        ("ordem", "zonas,identificacao"),
    ])
    _, _, secoes = _configuracao_relatorio("scouting-individual", dados, UtilizadorFalso(PerfilEnum.treinador))
    assert secoes == ["fotografia", "zonas", "identificacao"]
    _, _, vazias = _configuracao_relatorio("plano-jogo", FormData([("formato", "facil")]), UtilizadorFalso(PerfilEnum.treinador))
    assert vazias == _secoes_padrao("plano-jogo", "facil")


def test_configurador_tem_selecao_arrastar_previsualizacao_e_predefinicoes():
    html = (TEMPLATES / "exportacoes" / "_relatorio_formulario.html").read_text(encoding="utf-8")
    for marcador in ("draggable=\"true\"", "Pré-visualizar", "Descarregar PDF", "Guardar predefinição", "Selecionar tudo", "Repor formato"):
        assert marcador in html


def test_estatisticas_sao_escolhidas_individualmente_antes_da_exportacao():
    formulario = (TEMPLATES / "exportacoes" / "_relatorio_formulario.html").read_text(encoding="utf-8")
    rota = (ROOT / "backend" / "routers" / "exportacoes.py").read_text(encoding="utf-8")
    assert 'name="estatisticas"' in formulario
    assert 'dados.getlist("estatisticas")' in rota
    assert "campo in STAT_FIELDS" in rota


def test_scouting_individual_facil_tem_cartoes_fotografia_e_texto_curto():
    html = (TEMPLATES / "relatorios" / "scouting_individual_facil.html").read_text(encoding="utf-8")
    assert 'class="players"' in html
    assert 'class="player"' in html
    assert "fotografias.get(j.id)" in html
    assert "truncate(180)" in html
    assert "stat_fields" in html
    assert 'class="portrait"' in html
    assert 'class="stats"' in html
    assert "Pontos fortes" in html
    assert "Pontos a explorar" in html
    assert "Movimentos preferenciais" in html
    assert "Como defender" in html
    assert "j.idade" in html
    assert "j.peso_kg" in html


def test_restantes_relatorios_faceis_tem_modelos_visuais_proprios():
    marcadores = {
        "roster_facil.html": ("easy-roster", "fotografias.get(j.id)", "Referência rápida"),
        "scouting_coletivo_facil.html": ("Quando defendemos", "Quando atacamos", "Jogadores-chave"),
        "plano_jogo_facil.html": ("briefing da equipa", "O nosso cinco", "Convocados"),
    }
    for ficheiro, esperados in marcadores.items():
        html = (TEMPLATES / "relatorios" / ficheiro).read_text(encoding="utf-8")
        assert '_documento.html' not in html
        for esperado in esperados:
            assert esperado in html


def test_relatorios_faceis_com_jogadores_apresentam_fotografias():
    for ficheiro in (
        "roster_facil.html",
        "scouting_individual_facil.html",
        "scouting_coletivo_facil.html",
        "plano_jogo_facil.html",
    ):
        html = (TEMPLATES / "relatorios" / ficheiro).read_text(encoding="utf-8")
        assert "fotografia" in html
        assert "easy-photo" in html or 'class="photo"' in html


def test_relatorios_faceis_validam_fotografias_antes_de_renderizar():
    rota = (ROOT / "backend" / "routers" / "exportacoes.py").read_text(encoding="utf-8")
    roster = (TEMPLATES / "relatorios" / "roster_facil.html").read_text(encoding="utf-8")
    individual = (TEMPLATES / "relatorios" / "scouting_individual_facil.html").read_text(encoding="utf-8")
    assert "fotografias={j.id: _fotografia_embebida(j.fotografia)" in rota
    assert "fotografias.get(j.id)" in roster
    assert "fotografias.get(j.id)" in individual
    assert 'alt="{{ j.nome }}"' not in roster


def test_quadro_individual_permite_escolher_blocos_no_pendente():
    html = (TEMPLATES / "scouting" / "individual.html").read_text(encoding="utf-8")
    script = (ROOT / "frontend" / "static" / "js" / "dashboard-customization.js").read_text(encoding="utf-8")
    assert "data-customizable-dashboard" in html
    assert "data-dashboard-customizer-anchor" in html
    assert 'data-dashboard-widget="leitura-{{ categoria }}"' in html
    assert "dashboard-customizer-menu" in script
    assert "/dashboard/preferencias" in script


def test_formulario_dinamico_transporta_token_da_sessao():
    html = (TEMPLATES / "exportacoes" / "_relatorio_formulario.html").read_text(encoding="utf-8")
    script = (ROOT / "frontend" / "static" / "js" / "report-hub.js").read_text(encoding="utf-8")
    assert 'name="csrf_token"' in html
    assert "request.session.get('_csrf'" in html
    assert "credentials:'same-origin'" in script


def test_relatorios_estao_centralizados_em_cartoes_com_modal():
    central = (TEMPLATES / "scouting" / "relatorios.html").read_text(encoding="utf-8")
    assert central.count('class="report-hub-card"') == 4
    assert "report-hub-dialog" in central
    assert "report-hub.js" in central
    for ficheiro in ("equipas/plantel.html", "scouting/individual_lista.html", "scouting/coletivo.html", "scouting/plano_jogo.html"):
        conteudo = (TEMPLATES / ficheiro).read_text(encoding="utf-8")
        assert "Exportar relatório" not in conteudo


def test_relatorio_plantel_usa_o_adversario_em_analise():
    central = (TEMPLATES / "scouting" / "relatorios.html").read_text(encoding="utf-8")
    rota = (ROOT / "backend" / "routers" / "exportacoes.py").read_text(encoding="utf-8")
    documento = (TEMPLATES / "relatorios" / "_documento.html").read_text(encoding="utf-8")
    assert 'data-report-type="roster" data-report-target="{{ adversario.id }}"' in central
    assert 'tipo in {"roster", "scouting-individual", "scouting-coletivo"}' in rota
    assert "j.numero or '—'" in documento
    assert "j.posicao_principal" in documento


def test_fragmento_e_inicializador_do_popup_existem():
    rota = (ROOT / "backend" / "routers" / "exportacoes.py").read_text(encoding="utf-8")
    script = (ROOT / "frontend" / "static" / "js" / "report-hub.js").read_text(encoding="utf-8")
    assert '/fragmento"' in rota
    assert "initReportBuilder" in script
    assert "showModal" in script


def test_documento_omite_seccoes_sem_conteudo_por_condicao():
    html = (TEMPLATES / "relatorios" / "_documento.html").read_text(encoding="utf-8")
    assert "and adversario.observacoes" in html
    assert "and convocados" in html
    assert "and plano.situacoes_especiais" in html


def test_migracao_e_modelo_de_predefinicoes_estao_registados():
    migracao = ROOT / "backend" / "migrations" / "versions" / "0050_predefinicoes_relatorios.py"
    main = (ROOT / "backend" / "main.py").read_text(encoding="utf-8")
    assert migracao.is_file()
    assert "import models.relatorio_exportacao" in main

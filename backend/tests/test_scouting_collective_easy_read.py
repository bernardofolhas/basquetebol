import base64
import asyncio
from datetime import date
from io import BytesIO
import os
from pathlib import Path
from types import SimpleNamespace as Item

from PIL import Image, ImageDraw
from pypdf import PdfReader
from starlette.templating import Jinja2Templates
from weasyprint import HTML

from formatacao import data_pt
from models.scouting import STAT_FIELDS
from paths import STATIC_DIR, TEMPLATES_DIR
from routers.exportacoes import (
    _acoes_principais_coletivas,
    _caracteristicas_cinco_coletivo,
    _campos_estatisticos_coletivos,
    _contexto_configurador,
    _destaque_estatistico_coletivo,
    _guardar_destaque_estatistico_coletivo,
    _grupos_resposta_coletiva,
    _indicadores_coletivos,
    _media_exibida_coletiva,
    _normalizar_secoes_coletivas,
    _opcoes_defensivas_coletivas,
    _passos_setplay_pdf,
    _playbook_coletivo,
    _resultados_recentes_coletivos,
    guardar_destaque_estatistico,
)
from services.desenho_service import empacotar_desenho_editavel, imagem_estatica_data_uri
from services.pdf_service import preparar_contexto_pdf, simbolo_cabecalho_sem_fundo


def test_simbolos_opacos_assumem_o_fundo_do_cabecalho(monkeypatch):
    imagem = Image.new("RGB", (64, 64), "#080808")
    ImageDraw.Draw(imagem).ellipse((12, 12, 52, 52), fill="#f4c542")
    buffer = BytesIO()
    imagem.save(buffer, format="PNG")
    uri = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")

    contexto = preparar_contexto_pdf(
        Item(state=Item(identidade_clube=None)),
        {"tipo_relatorio": "scouting-coletivo", "simbolo_adversario": uri},
    )
    resultado = Image.open(BytesIO(base64.b64decode(contexto["simbolo_adversario"].split(",", 1)[1])))
    assert resultado.getpixel((0, 0))[3] == 0
    assert resultado.getpixel((32, 32)) == (244, 197, 66, 255)

    monkeypatch.setattr("services.pdf_service.caminho_ficheiro_logo", lambda _base, url: Path(__file__) if url else None)
    monkeypatch.setattr("services.pdf_service.imagem_estatica_data_uri", lambda _caminho, _mime: uri)
    contexto_clube = preparar_contexto_pdf(
        Item(state=Item(identidade_clube=None)),
        {"tipo_relatorio": "scouting-coletivo", "identidade": {"logo_principal": "/static/simbolo-clube.png"}},
    )
    clube = Image.open(BytesIO(base64.b64decode(contexto_clube["identidade"]["logo_principal"].split(",", 1)[1])))
    assert clube.getpixel((0, 0))[3] == 0
    assert clube.getpixel((32, 32)) == (244, 197, 66, 255)

    imagem_transparente = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    ImageDraw.Draw(imagem_transparente).ellipse((12, 12, 52, 52), fill="#f4c542")
    buffer = BytesIO()
    imagem_transparente.save(buffer, format="PNG")
    uri_transparente = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
    assert simbolo_cabecalho_sem_fundo(uri_transparente) == uri_transparente


def test_medias_calculadas_e_percentagens_sem_media_manual():
    jogos = [Item(**{campo: None for campo in STAT_FIELDS}) for _ in range(2)]
    jogos[0].pontos, jogos[1].pontos = 80, 90
    jogos[0].dois_c, jogos[1].dois_c = 20, 22
    jogos[0].dois_t, jogos[1].dois_t = 40, 44
    adversario = Item(media_coletiva=Item(usar_manual=False), estatisticas_coletivas=jogos)

    media = _media_exibida_coletiva(adversario)
    indicadores = _indicadores_coletivos(media, ["pontos", "dois_c", "dois_t"])

    assert media["pontos"] == 85
    assert indicadores == [{"nome": "PTS", "valor": "85.0"}, {"nome": "2P%", "valor": "50%"}]
    assert _destaque_estatistico_coletivo("2P%", "positivo", indicadores) == {"codigo": "2P%", "tom": "positivo"}
    assert _destaque_estatistico_coletivo("PTS", "negativo", indicadores) == {"codigo": "PTS", "tom": "negativo"}
    assert _destaque_estatistico_coletivo("FG%", "positivo", indicadores) is None
    assert _destaque_estatistico_coletivo("PTS", "neutro", indicadores) is None


def test_destaque_fta_nao_e_substituido_pela_percentagem():
    media = {campo: None for campo in STAT_FIELDS}
    media.update(pontos=82, ll_c=18, ll_t=24)
    indicadores = _indicadores_coletivos(media, ["ll_c", "ll_t"], "FTA")
    assert [indicador["nome"] for indicador in indicadores] == ["FTM", "FTA"]
    assert _destaque_estatistico_coletivo("FTA", "negativo", indicadores) == {
        "codigo": "FTA", "tom": "negativo"
    }
    assert _destaque_estatistico_coletivo("FTA", "negativo", []) is None
    campos = _campos_estatisticos_coletivos([], "FTA")
    assert "pontos" in campos and "ll_c" in campos and "ll_t" in campos
    assert _destaque_estatistico_coletivo(
        "FTA", "negativo", _indicadores_coletivos(media, campos, "FTA")
    ) == {"codigo": "FTA", "tom": "negativo"}


def test_destaque_guardado_pode_ser_positivo_negativo_ou_retirado(monkeypatch):
    adversario = Item(estatistica_destaque=None, estatistica_destaque_tom=None,
                     jogadores=[], resultados=[], lideres=[])
    commits = []
    db = Item(commit=lambda: commits.append(True))
    equipa = Item(id=3, nome="Equipa")
    monkeypatch.setattr(
        "routers.exportacoes._alvo_relatorio",
        lambda tipo, alvo_id, sessao, utilizador: (adversario, equipa, "Rival"),
    )
    monkeypatch.setattr("routers.exportacoes._predefinicoes_relatorio", lambda *args: [])

    class Pedido:
        headers = {"X-Requested-With": "XMLHttpRequest"}

        def __init__(self, dados):
            self.dados = dados

        async def form(self):
            return self.dados

    for tom in ("positivo", "negativo"):
        resposta = asyncio.run(guardar_destaque_estatistico(
            7, Pedido({"estatistica_destaque": "FTA", "estatistica_destaque_tom": tom}), db, Item()
        ))
        assert resposta.status_code == 200
        assert adversario.estatistica_destaque == "FTA"
        assert adversario.estatistica_destaque_tom == tom
        configurador = _contexto_configurador("scouting-coletivo", 7, db, Item())
        assert configurador["estatistica_destaque_selecionada"] == "FTA"
        assert configurador["estatistica_destaque_tom"] == tom
        asyncio.run(guardar_destaque_estatistico(
            7, Pedido({"estatistica_destaque": "FTA", "estatistica_destaque_tom": tom,
                       "limpar_destaque": "1"}), db, Item()
        ))
        assert adversario.estatistica_destaque is None
        assert adversario.estatistica_destaque_tom is None
        assert _contexto_configurador("scouting-coletivo", 7, db, Item())[
            "estatistica_destaque_selecionada"
        ] == ""
    assert len(commits) == 4


def test_acoes_principais_nao_incluem_momentos_reservados_ao_playbook():
    conceito = Item(setplay=Item(nome="Horns"))
    momento = Item(setplay=Item(nome="ATO"))
    adversario = Item(conceitos_ofensivos=[conceito], momentos_playbook=[momento])
    assert _acoes_principais_coletivas(adversario) == [conceito]


def test_resultados_recentes_so_incluem_jogos_com_marcador_e_respeitam_a_selecao():
    resultados = [
        Item(id=numero, data=date(2026, 10, numero), pontos_marcados=70 + numero,
             pontos_sofridos=65, oponente=f'Equipa {numero}')
        for numero in range(1, 7)
    ]
    resultados.append(Item(id=7, data=date(2026, 10, 7), pontos_marcados=None,
                           pontos_sofridos=65, oponente='Sem marcador'))
    adversario = Item(resultados=resultados)

    assert [r.id for r in _resultados_recentes_coletivos(adversario)] == [6, 5, 4, 3, 2]
    assert [r.id for r in _resultados_recentes_coletivos(adversario, [3, 6, 1])] == [6, 3]
    assert _resultados_recentes_coletivos(adversario, []) == []


def test_playbook_coletivo_mantem_jogadas_separadas_e_observacoes_por_cena():
    primeiro = Item(id=11, nome='Horns', descricao='Entrada central', passos=[
        Item(desenho='{}', imagem_coach=None, observacao='Bloquear à esquerda'),
        Item(desenho='{}', imagem_coach=None, observacao='Abrir para o canto'),
    ])
    segundo = Item(id=12, nome='Stagger', descricao=None, passos=[
        Item(desenho='{}', imagem_coach=None, observacao='Libertar o lançador'),
    ])
    vazio = Item(id=13, nome='Por desenhar', descricao=None, passos=[
        Item(desenho=None, imagem_coach=None, observacao=''),
    ])
    adversario = Item(momentos_playbook=[Item(setplay=primeiro), Item(setplay=segundo), Item(setplay=vazio)])
    passos = {
        11: [{'ordem': 1, 'imagem': 'cena-1', 'observacao': 'Bloquear à esquerda'},
             {'ordem': 2, 'imagem': 'cena-2', 'observacao': 'Abrir para o canto'}],
        12: [{'ordem': 1, 'imagem': 'cena-3', 'observacao': 'Libertar o lançador'}],
    }

    jogadas = _playbook_coletivo(adversario, passos)
    assert [jogada['titulo'] for jogada in jogadas] == ['Horns', 'Stagger']
    assert [passo['observacao'] for passo in jogadas[0]['passos']] == [
        'Bloquear à esquerda', 'Abrir para o canto'
    ]


def test_cena_de_campo_inteiro_mantem_o_campo_inteiro_no_pdf():
    imagem = imagem_estatica_data_uri(STATIC_DIR / 'campos' / 'campo_completo.png')
    desenho = empacotar_desenho_editavel(imagem, {
        'campoTipo': 'completo', 'largura': 697, 'altura': 1222,
        'objectos': [{'tipo': 'seta', 'pontos': [{'x': 100, 'y': 200}, {'x': 200, 'y': 300}]}],
    })
    setplay = Item(passos=[Item(ordem=0, desenho=desenho, imagem_coach=None, observacao='Campo inteiro')])

    passo = _passos_setplay_pdf(setplay)[0]
    imagem_pdf = Image.open(BytesIO(base64.b64decode(passo['imagem'].split(',', 1)[1])))
    assert imagem_pdf.size == (697, 1222)
    assert passo['observacao'] == 'Campo inteiro'


def test_resultados_e_playbook_ficam_em_blocos_independentes_no_fim_da_leitura_facil():
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    templates.env.filters['data_pt'] = data_pt
    campo = imagem_estatica_data_uri(STATIC_DIR / 'campos' / 'campo_meio.png')
    contexto = {
        'secoes_set': {'resultados', 'playbook'}, 'blocos_coletivos': {},
        'respostas_grupos': [], 'alvo_nome': 'Rivals BC',
        'identidade': {'cor_principal': '#d60b18', 'cor_principal_escura': '#a00812',
                       'texto_sobre_principal': '#ffffff', 'logo_principal': None},
        'resultados_recentes': [Item(id=1, data=date(2026, 10, 2), oponente='Queluz',
                                     em_casa=True, competicao='Liga', pontos_marcados=80, pontos_sofridos=72)],
        'playbook_coletivo': [
            {'titulo': 'Horns', 'passos': [
                {'passo': 1, 'imagem': campo, 'observacao': 'Bloqueio no topo'},
                {'passo': 2, 'imagem': campo, 'observacao': 'Passe para o canto'},
            ]},
            {'titulo': 'Stagger', 'passos': [
                {'passo': 1, 'imagem': campo, 'observacao': 'Saída do lançador'},
            ]},
        ],
    }
    template = templates.get_template('relatorios/scouting_coletivo_facil_v2.html')
    html = template.render(contexto)
    assert html.index('Últimos resultados') < html.index('Playbook do adversário')
    assert html.count('class="pdf-play-card"') == 2
    assert html.count('class="pdf-play-step"') == 3
    assert html.index('Bloqueio no topo') < html.index('Passe para o canto') < html.index('Stagger')
    assert 'Queluz' in html and '80–72' in html
    pdf = HTML(string=html).write_pdf()
    if destino := os.getenv('SCOUTING_PLAYBOOK_QA_PDF'):
        Path(destino).write_bytes(pdf)
    texto_pdf = ' '.join(pagina.extract_text() for pagina in PdfReader(BytesIO(pdf)).pages)
    for texto in ('Queluz', 'Horns', 'Stagger', 'Bloqueio no topo', 'Passe para o canto', 'Saída do lançador'):
        assert texto in texto_pdf

    contexto['secoes_set'] = {'resultados'}
    assert 'Playbook do adversário</h2>' not in template.render(contexto)
    contexto['secoes_set'] = {'playbook'}
    assert 'Últimos resultados</h2>' not in template.render(contexto)
    contexto['playbook_coletivo'] = []
    assert 'Playbook do adversário</h2>' not in template.render(contexto)


def test_relatorio_completo_apresenta_o_playbook_depois_das_outras_secoes():
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    templates.env.filters['data_pt'] = data_pt
    contexto = {
        'identidade': {'cor_principal': '#d60b18', 'cor_principal_escura': '#a00812',
                       'texto_sobre_principal': '#ffffff', 'logo_principal': None},
        'secoes_set': {'resultados', 'playbook'}, 'alvo_nome': 'Rivals BC',
        'simbolo_adversario': None, 'adversario': Item(observacoes=None),
        'equipa': Item(nome='Nossa equipa'), 'itens_coletivos': {},
        'resultados_recentes': [Item(data=date(2026, 10, 2), oponente='Queluz',
                                     em_casa=True, competicao='Liga', pontos_marcados=80, pontos_sofridos=72)],
        'playbook_coletivo': [{'titulo': 'Horns', 'passos': [
            {'passo': 1, 'imagem': None, 'observacao': 'Entrada central'},
        ]}],
    }
    html = templates.get_template('relatorios/scouting_coletivo_completo.html').render(contexto)
    assert html.index('Últimos resultados') < html.index('Playbook do adversário')
    assert html.count('class="pdf-play-card"') == 1
    assert 'Entrada central' in html


def test_respostas_agrupadas_ignoram_blocos_nao_destacados():
    blocos = {
        "resposta": [Item(titulo="Fechar linha", categoria="Defesa", destaque=True)],
        "transicao": [Item(titulo="Correr para trás", categoria="Transição", destaque=False)],
    }
    grupos = _grupos_resposta_coletiva(blocos)
    assert grupos[0]["blocos"][0].titulo == "Fechar linha"
    assert grupos[2]["blocos"] == []


def test_predefinicoes_antigas_separam_analise_e_regras():
    assert _normalizar_secoes_coletivas(["perfil", "ataque", "defesa", "resposta"]) == [
        "perfil", "analise", "regras_coberturas", "resposta"
    ]


def test_titulares_recebem_caracteristicas_e_opcoes_ativas_sem_ruido():
    relacao = lambda nome, nota, destaque=False: Item(
        item=Item(nome=nome, ativo=True, categoria="caracteristica"),
        avaliacao=nota, destaque=destaque, ordem_destaque=None,
    )
    jogador = Item(id=7, itens=[
        relacao("Sem avaliação", 0), relacao("P&R central", 4),
        relacao("Ressalto ofensivo", 5, True),
    ])
    assert _caracteristicas_cinco_coletivo([jogador]) == {
        7: ["Ressalto ofensivo", "P&R central"]
    }
    opcoes = Item(bloqueio_central=True, bloqueio_central_notas="Push ou switch",
                  bloqueio_lateral=True, bloqueio_lateral_notas=" ",
                  handoff=False, handoff_notas="Não mostrar")
    assert _opcoes_defensivas_coletivas(opcoes) == [
        {"nome": "Bloqueios diretos centrais", "notas": "Push ou switch"}
    ]


def test_leitura_facil_coletiva_renderiza_uma_pagina():
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    templates.env.filters["data_pt"] = data_pt
    jogador = lambda numero: Item(id=numero, nome=f"Jogador {numero}", numero=numero, posicao_principal="Base")
    titulares = [Item(jogador=jogador(numero)) for numero in range(1, 6)]
    perfil = lambda titulo, categoria, avaliacao: Item(titulo=titulo, categoria=categoria, avaliacao=avaliacao, descricao="Leitura rápida")
    ataque = [perfil(nome, "Ataque", 4) for nome in ("Transição", "P&R central", "Handoff", "Ressalto ofensivo")]
    defesa = [perfil(nome, "Defesa", 3) for nome in ("Pressão na bola", "Switch", "Handoff", "Proteção do aro")]
    chaves = [Item(titulo=nome, descricao="Mensagem curta para a equipa", destaque=True) for nome in ("Ritmo alto", "P&R central", "Ressalto ofensivo")]
    resposta = Item(titulo="Controlar transição", descricao="Cinco atrás da bola", destaque=True, categoria="Defesa")
    prioridades = {
        "resposta": [resposta],
        "prioridade_ofensiva": [Item(titulo="Forçar P&R lateral", descricao="Negar o meio", destaque=True, categoria="P&R")],
        "transicao": [Item(titulo="Proteger o cesto", descricao="Regressar cedo", destaque=True)],
        "ressalto": [Item(titulo="Fechar o 5", descricao="Box-out coletivo", destaque=True)],
    }
    jogadas = [Item(setplay=Item(id=numero, nome=f"Ação {numero}", descricao="Entrada para P&R")) for numero in range(1, 4)]
    campo = imagem_estatica_data_uri(STATIC_DIR / "campos" / "campo_meio.png")
    contexto = {
        "identidade": {"cor_principal": "#d60b18", "cor_principal_escura": "#a00812", "texto_sobre_principal": "#ffffff", "logo_principal": None},
        "alvo_nome": "Rivals BC", "simbolo_adversario": None, "nome_autor": "Treinador",
        "adversario": Item(observacoes="Equipa rápida e agressiva", momentos_playbook=jogadas),
        "jogo_referencia": Item(competicao="Liga", data=date(2026, 10, 12), hora="15:00", local="Pavilhão Municipal"),
        "secoes_set": {"identidade", "chaves", "cinco_rotacao", "jogadores_chave", "estatisticas", "perfil", "resposta", "diagramas"},
        "blocos_coletivos": {"chave": chaves, "resposta": [resposta]},
        "perfil_ataque": ataque, "perfil_defesa": defesa,
        "cinco_previsto": titulares, "rotacoes_previstas": [Item(jogador=jogador(6))],
        "substituicoes_por_titular": {1: {
            1: Item(jogador=Item(nome="Reserva Um")),
            2: Item(jogador=Item(nome="Reserva Dois")),
        }},
        "rotacoes_sem_titular": {}, "ha_rotacoes_sem_titular": False,
        "rotacoes_por_posicao": {"Base": [Item(jogador=jogador(6))]},
        "fotografias": {}, "caracteristicas_cinco": {1: ["P&R central", "Transição"]},
        "jogadores_prioritarios": [
            {"jogador": Item(id=numero, nome=nome, posicao_principal=posicao),
             "caracteristica": caracteristica,
             "liderancas": ["Melhor marcador", "Melhor assistente"] if numero == 1 else []}
            for numero, nome, posicao, caracteristica in (
                (1, "Gus Goerzen", "Extremo", "Lançador Catch and Shoot"),
                (2, "Lamine Banora", "Poste", "Participação no ressalto ofensivo"),
                (3, "Thomas Jervis", "Poste", "Defesa a jogadores interiores"),
                (4, "Miguel Carmine", "Base", "Criação de lançamento após bloqueio direto"),
            )
        ],
        "indicadores_coletivos": [{"nome": nome, "valor": "85.0"} for nome in ("PTS", "2P%", "3P%", "LL%", "OREB", "DREB", "AST", "TOV", "STL", "EFF")],
        "principais_caracteristicas": [], "respostas_grupos": _grupos_resposta_coletiva(prioridades),
        "jogadas_coletivas": jogadas,
        "passos_setplay": {numero: [Item(imagem=campo, observacao="Movimento e leitura de ajudas")] for numero in range(1, 4)},
    }
    html = templates.get_template("relatorios/scouting_coletivo_facil_v2.html").render(contexto)
    assert html.count('class="play-card"') == 3
    assert html.count("<header><h3>Ação") == 3
    assert "background:#cf0000" in html
    assert html.count('class="lineup-rotation-slot"') == 5
    assert "1.ª →" in html and "2.ª →" in html
    pdf = HTML(string=html).write_pdf()
    if destino := os.getenv("SCOUTING_QA_PDF"):
        Path(destino).write_bytes(pdf)

    paginas = PdfReader(BytesIO(pdf)).pages
    assert len(paginas) == 1
    texto_pdf = " ".join(paginas[0].extract_text().split())
    for texto in ("Gus Goerzen", "Lamine Banora", "Thomas Jervis", "Reserva Um", "Reserva Dois", "Participação no ressalto ofensivo", "Criação de lançamento após bloqueio direto", "Melhor marcador", "Melhor assistente"):
        assert texto in texto_pdf
    assert "Cinco inicial" in html
    assert "<small>Dia</small>12/10/2026" in html
    assert "<small>Hora</small>15:00" in html
    assert "<small>Pavilhão</small>Pavilhão Municipal" in html
    assert "<small>Treinador</small>" not in html
    assert "Treinador" not in texto_pdf
    assert "Estatística - Média de época" in html
    assert "Jogadores mais influentes" in html
    assert ".priority-player{display:flex;" in html
    assert ".priority-copy{display:block;flex:1 1 0;min-width:0}" in html
    assert "Ações principais" in html
    assert "Ações principais / Playbook" not in html
    assert 'class="stat is-positive"' not in html
    assert "Perfil coletivo" in html
    assert "Nossa resposta" in html
    assert "Chaves da equipa" in html
    assert "P&amp;R central" in html
    assert "Forçar P&R lateral" not in html
    assert "Regras defensivas mais utilizadas" not in html

    contexto["destaque_estatistico"] = {"codigo": "PTS", "tom": "positivo"}
    positivo = templates.get_template("relatorios/scouting_coletivo_facil_v2.html").render(contexto)
    assert '<div class="stat is-positive"><small>PTS</small>' in positivo
    assert positivo.count('class="stat is-positive"') == 1
    contexto["destaque_estatistico"] = {"codigo": "2P%", "tom": "negativo"}
    negativo = templates.get_template("relatorios/scouting_coletivo_facil_v2.html").render(contexto)
    assert '<div class="stat is-negative"><small>2P%</small>' in negativo
    assert negativo.count('class="stat is-negative"') == 1
    contexto["destaque_estatistico"] = None

    contexto["secoes_set"].add("regras_coberturas")
    contexto["opcoes_defensivas_facil"] = [{"nome": "Bloqueios diretos centrais", "notas": "Push ou switch"}]
    com_defesa = templates.get_template("relatorios/scouting_coletivo_facil_v2.html").render(contexto)
    assert "Regras defensivas mais utilizadas" in com_defesa
    assert "Push ou switch" in com_defesa
    texto_pdf = "\n".join(
        pagina.extract_text() for pagina in PdfReader(BytesIO(HTML(string=com_defesa).write_pdf())).pages
    )
    assert "Push ou switch" in texto_pdf
    contexto["opcoes_defensivas_facil"] = []
    sem_dados = templates.get_template("relatorios/scouting_coletivo_facil_v2.html").render(contexto)
    assert "Regras defensivas mais utilizadas" not in sem_dados

    contexto["secoes_set"].add("analise")
    contexto["itens_coletivos"] = {
        "ataque_forte": [Item(item=Item(nome="Pressão após cesto"), observacao="Ataca cedo", valor=None)]
    }
    com_ataque = templates.get_template("relatorios/scouting_coletivo_facil_v2.html").render(contexto)
    assert "Análise técnico-tática · ataque" in com_ataque
    assert "Pressão após cesto" in com_ataque

    contexto["secoes_set"] = {"chaves"}
    so_chaves = templates.get_template("relatorios/scouting_coletivo_facil_v2.html").render(contexto)
    assert "Ritmo alto" in so_chaves
    assert "Perfil coletivo" not in so_chaves
    assert "Controlar transição" not in so_chaves
    assert "Pressão após cesto" not in so_chaves

    contexto["secoes_set"] = {"perfil"}
    so_perfil = templates.get_template("relatorios/scouting_coletivo_facil_v2.html").render(contexto)
    assert "Perfil coletivo" in so_perfil
    assert "Ritmo alto" not in so_perfil
    assert "Controlar transição" not in so_perfil

    contexto["secoes_set"] = {"resposta"}
    so_resposta = templates.get_template("relatorios/scouting_coletivo_facil_v2.html").render(contexto)
    assert "Controlar transição" in so_resposta
    assert "Ritmo alto" not in so_resposta
    assert "Perfil coletivo" not in so_resposta

    contexto["secoes_set"] = {"regras_coberturas"}
    contexto["opcoes_defensivas_facil"] = [{"nome": "Bloqueios diretos centrais", "notas": "Push ou switch"}]
    so_regras = templates.get_template("relatorios/scouting_coletivo_facil_v2.html").render(contexto)
    assert "Push ou switch" in so_regras
    assert "Pressão após cesto" not in so_regras

    contexto["secoes_set"] = {"identidade"}
    contexto["jogo_referencia"] = None
    sem_jogo = templates.get_template("relatorios/scouting_coletivo_facil_v2.html").render(contexto)
    assert sem_jogo.count("Por definir") == 3

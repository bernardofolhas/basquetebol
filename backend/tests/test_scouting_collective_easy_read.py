from datetime import date
from io import BytesIO
import os
from pathlib import Path
from types import SimpleNamespace as Item

from pypdf import PdfReader
from starlette.templating import Jinja2Templates
from weasyprint import HTML

from formatacao import data_pt
from models.scouting import STAT_FIELDS
from paths import STATIC_DIR, TEMPLATES_DIR
from routers.exportacoes import (
    _caracteristicas_cinco_coletivo,
    _grupos_resposta_coletiva,
    _indicadores_coletivos,
    _media_exibida_coletiva,
    _normalizar_secoes_coletivas,
    _opcoes_defensivas_coletivas,
)
from services.desenho_service import imagem_estatica_data_uri


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
        "jogo_referencia": Item(competicao="Liga", data=date(2026, 10, 12)),
        "secoes_set": {"identidade", "chaves", "cinco_rotacao", "jogadores_chave", "estatisticas", "perfil", "resposta", "diagramas"},
        "blocos_coletivos": {"chave": chaves, "resposta": [resposta]},
        "perfil_ataque": ataque, "perfil_defesa": defesa,
        "cinco_previsto": titulares, "rotacoes_previstas": [Item(jogador=jogador(6))],
        "rotacoes_por_posicao": {"Base": [Item(jogador=jogador(6))]},
        "fotografias": {}, "caracteristicas_cinco": {1: ["P&R central", "Transição"]},
        "jogadores_prioritarios": [{"jogador": jogador(numero), "caracteristica": "Lançamento exterior"} for numero in range(1, 5)], "indicadores_coletivos": [{"nome": nome, "valor": "85.0"} for nome in ("PTS", "2P%", "3P%", "LL%", "OREB", "DREB", "AST", "TOV", "STL", "EFF")],
        "principais_caracteristicas": [], "respostas_grupos": _grupos_resposta_coletiva(prioridades),
        "jogadas_coletivas": jogadas,
        "passos_setplay": {numero: [Item(imagem=campo, observacao="Movimento e leitura de ajudas")] for numero in range(1, 4)},
    }
    html = templates.get_template("relatorios/scouting_coletivo_facil_v2.html").render(contexto)
    pdf = HTML(string=html).write_pdf()
    if destino := os.getenv("SCOUTING_QA_PDF"):
        Path(destino).write_bytes(pdf)

    assert len(PdfReader(BytesIO(pdf)).pages) == 1
    assert "Cinco inicial" in html
    assert "Números da equipa" in html
    assert "Perfil coletivo" in html
    assert "Nossa resposta" in html
    assert "Chaves da equipa" in html
    assert "P&amp;R central" in html
    assert "Forçar P&R lateral" not in html
    assert "Regras e coberturas" not in html

    contexto["secoes_set"].add("regras_coberturas")
    contexto["opcoes_defensivas_facil"] = [{"nome": "Bloqueios diretos centrais", "notas": "Push ou switch"}]
    com_defesa = templates.get_template("relatorios/scouting_coletivo_facil_v2.html").render(contexto)
    assert "Regras e coberturas" in com_defesa
    assert "Push ou switch" in com_defesa
    texto_pdf = "\n".join(
        pagina.extract_text() for pagina in PdfReader(BytesIO(HTML(string=com_defesa).write_pdf())).pages
    )
    assert "Push ou switch" in texto_pdf
    contexto["opcoes_defensivas_facil"] = []
    sem_dados = templates.get_template("relatorios/scouting_coletivo_facil_v2.html").render(contexto)
    assert "Regras e coberturas" not in sem_dados

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

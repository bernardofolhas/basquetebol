"""Regressão visual e de conteúdo para dois cartões individuais por A4."""

from io import BytesIO
import os
from pathlib import Path
from types import SimpleNamespace as Item

from pypdf import PdfReader
from starlette.templating import Jinja2Templates
from weasyprint import HTML

from paths import STATIC_DIR, TEMPLATES_DIR
from services.desenho_service import imagem_estatica_data_uri
from services.scouting_individual_service import avaliacao_meta


def test_dois_cartoes_individuais_completos_cabem_num_a4():
    atletas = []
    perfis = {}
    ultimo_jogo = {}
    campos = ["pontos", "fg_c", "fg_t", "tres_c", "tres_t", "assistencias", "ress_total"]
    for indice, nome in ((1, "Ana Martins"), (2, "Beatriz Silva")):
        jogador = Item(
            id=indice, nome=nome, numero=str(indice), posicao_principal="Extremo",
            posicao_alternativa="Base", altura_cm=178, peso_kg=68,
            mao_dominante="Direita", ficha=Item(resumo="Ataca cedo\nLança após passe\nDefende com energia"),
            zonas=[Item(zona="topo"), Item(zona="ala_direita")],
            media_epoca=Item(pontos=14, fg_c=5, fg_t=10, tres_c=2, tres_t=5, assistencias=3, ress_total=4),
        )
        atletas.append(jogador)
        ultimo_jogo[indice] = Item(pontos=17, fg_c=6, fg_t=12, tres_c=3, tres_t=6, assistencias=4, ress_total=5)
        avaliacoes = [
            {"relacao": Item(item=Item(nome=f"Característica {numero}"), observacao="Nota útil"),
             "avaliacao": avaliacao_meta(numero)}
            for numero in range(1, 6)
        ]
        tendencias = [Item(item=Item(nome=f"Tendência {numero}"), observacao="Contexto curto") for numero in range(1, 4)]
        plano = [Item(item=Item(nome=f"Instrução {numero}"), observacao="Resposta curta", prioridade=numero) for numero in range(1, 4)]
        perfis[indice] = Item(avaliacoes=avaliacoes, tendencias=tendencias, game_plan=plano)

    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    campo = imagem_estatica_data_uri(STATIC_DIR / "campos" / "campo_meio.png")
    contexto = {
        "identidade": {"cor_principal": "#d60b18", "cor_principal_escura": "#a00812", "texto_sobre_principal": "#ffffff", "logo_principal": None},
        "alvo_nome": "Adversário", "simbolo_adversario": None,
        "atletas": atletas, "destaques_atletas": perfis, "ultimo_jogo": ultimo_jogo,
        "secoes_set": {"fotografia", "identificacao", "observacoes", "zonas", "estatisticas", "avaliacoes", "tendencias", "game_plan"},
        "stat_fields": campos, "stat_codes": {campo: campo.upper() for campo in campos},
        "fotografias": {}, "campo_meio": campo, "data_exportacao": "02/10/2026",
    }
    html = templates.get_template("relatorios/scouting_individual_facil.html").render(contexto)
    pdf = HTML(string=html).write_pdf()
    if destino := os.getenv("SCOUTING_INDIVIDUAL_QA_PDF"):
        Path(destino).write_bytes(pdf)
    paginas = PdfReader(BytesIO(pdf)).pages
    assert len(paginas) == 1
    assert round(float(paginas[0].mediabox.width)) == 595
    texto = " ".join(paginas[0].extract_text().split())
    for valor in ("Ana Martins", "Beatriz Silva", "HOTZONES", "Plano de jogo", "Contexto curto", "50.0%"):
        assert valor in texto
    for titulo in ("Características", "Tendências", "Último jogo", "Média da época"):
        assert titulo in html

    terceiro = Item(**vars(atletas[-1]))
    terceiro.id = 3
    terceiro.nome = "Clara Lopes"
    contexto["atletas"] = [*atletas, terceiro]
    perfis[3] = perfis[2]
    ultimo_jogo[3] = ultimo_jogo[2]
    tres_cartoes = templates.get_template("relatorios/scouting_individual_facil.html").render(contexto)
    paginas = PdfReader(BytesIO(HTML(string=tres_cartoes).write_pdf())).pages
    assert len(paginas) == 2
    assert "Ana Martins" in paginas[0].extract_text()
    assert "Beatriz Silva" in paginas[0].extract_text()
    assert "Clara Lopes" in paginas[1].extract_text()

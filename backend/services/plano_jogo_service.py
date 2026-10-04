"""Contexto e compatibilidade do plano de jogo estruturado."""

import unicodedata
from datetime import date
from pathlib import Path

from sqlalchemy.orm import Session

from models.jogo import ItemPlanoJogoBiblioteca, PlanoJogoItem
from models.playbook import Playbook, SetPlay
from paths import STATIC_DIR
from services.desenho_service import (
    compor_desenho_sobre_campo,
    decompor_desenho_editavel,
    normalizar_data_uri,
)


CATEGORIAS_PLANO = (
    ("chave_ataque", "Chaves do jogo · Ataque", "chaves_ataque"),
    ("chave_defesa", "Chaves do jogo · Defesa", "chaves_defesa"),
    ("movimento_ofensivo", "Movimentos ofensivos", "movimentos_ofensivos"),
    ("bloqueio_direto_lateral", "Bloqueio direto lateral", "bloqueio_direto_lateral"),
    ("bloqueio_direto_central", "Bloqueio direto central", "bloqueio_direto_central"),
    ("handoff", "Handoff", "handoff"),
    ("indiretos_entrada", "Indiretos de entrada", "indiretos_entrada"),
    ("indiretos_saida", "Indiretos de saída", "indiretos_saida"),
    ("bola_dentro", "Bola dentro", "bola_dentro"),
    ("situacoes_especiais", "Situações especiais", "situacoes_especiais"),
)
CAMPOS_POR_CATEGORIA = {categoria: campo for categoria, _, campo in CATEGORIAS_PLANO}


def jogo_em_preparacao(jogo, hoje: date | None = None) -> bool:
    """Um jogo pode ser preparado até ao próprio dia, nunca depois."""
    referencia = hoje or date.today()
    return bool(jogo and jogo.data and jogo.data >= referencia)


def jogos_em_preparacao(jogos, hoje: date | None = None) -> list:
    """Devolve apenas jogos não realizados, começando pelo mais próximo."""
    referencia = hoje or date.today()
    return sorted(
        (jogo for jogo in jogos if jogo_em_preparacao(jogo, referencia)),
        key=lambda jogo: (jogo.data, jogo.hora or "", jogo.id or 0),
    )


def normalizar_texto(valor: str | None) -> str:
    texto = unicodedata.normalize("NFKD", (valor or "").strip().lower())
    limpo = "".join(c for c in texto if not unicodedata.combining(c))
    return " ".join(limpo.split())[:240]


def convocados_plano(jogo):
    vistos = set()
    jogadores = []
    for convocado in sorted(jogo.convocados, key=lambda item: item.id or 0):
        jogador = convocado.jogador
        if jogador and jogador.id not in vistos:
            vistos.add(jogador.id)
            jogadores.append(jogador)
    return jogadores


def rotacoes_por_grupo(plano) -> dict[int, list]:
    grupos = {1: [], 2: [], 3: []}
    if not plano:
        return grupos
    for entrada in plano.grupos_rotacao:
        if entrada.grupo in grupos:
            grupos[entrada.grupo].append(entrada)
    return grupos


def itens_por_categoria(plano) -> dict[str, list]:
    resultado = {categoria: [] for categoria, _, _ in CATEGORIAS_PLANO}
    if not plano:
        return resultado
    for relacao in plano.itens:
        if relacao.item and relacao.item.categoria in resultado:
            resultado[relacao.item.categoria].append(relacao)
    return resultado


def conteudo_plano_por_categoria(plano) -> dict[str, list[str]]:
    """Prioriza as escolhas atuais e mantém legíveis os planos antigos."""
    grupos = itens_por_categoria(plano)
    resultado = {}
    for categoria, _, campo in CATEGORIAS_PLANO:
        escolhidos = [
            relacao.item.texto.strip()
            for relacao in grupos[categoria]
            if relacao.item and (relacao.item.texto or "").strip()
        ]
        legado = getattr(plano, campo, None) if plano else None
        resultado[categoria] = escolhidos or [
            linha.strip() for linha in (legado or "").splitlines() if linha.strip()
        ]
    return resultado


def biblioteca_por_categoria(db: Session, equipa_id: int) -> dict[str, list]:
    resultado = {categoria: [] for categoria, _, _ in CATEGORIAS_PLANO}
    itens = db.query(ItemPlanoJogoBiblioteca).filter(
        ItemPlanoJogoBiblioteca.equipa_id == equipa_id,
        ItemPlanoJogoBiblioteca.ativo.is_(True),
    ).order_by(ItemPlanoJogoBiblioteca.texto).all()
    for item in itens:
        if item.categoria in resultado:
            resultado[item.categoria].append(item)
    return resultado


def materializar_campos_legados(db: Session, plano, equipa_id: int) -> bool:
    """Transforma texto histórico numa entrada reutilizável sem perder conteúdo."""
    if not plano:
        return False
    existentes = itens_por_categoria(plano)
    alterado = False
    for categoria, _, campo in CATEGORIAS_PLANO:
        texto = (getattr(plano, campo, None) or "").strip()
        if not texto or existentes[categoria]:
            continue
        normalizado = normalizar_texto(texto)
        item = db.query(ItemPlanoJogoBiblioteca).filter(
            ItemPlanoJogoBiblioteca.equipa_id == equipa_id,
            ItemPlanoJogoBiblioteca.categoria == categoria,
            ItemPlanoJogoBiblioteca.texto_normalizado == normalizado,
        ).first()
        if not item:
            item = ItemPlanoJogoBiblioteca(
                clube_id=plano.clube_id,
                equipa_id=equipa_id,
                categoria=categoria,
                texto=texto,
                texto_normalizado=normalizado,
            )
            db.add(item)
            db.flush()
        db.add(PlanoJogoItem(
            clube_id=plano.clube_id,
            plano_jogo_id=plano.id,
            item_id=item.id,
            ordem=0,
        ))
        alterado = True
    return alterado


def sincronizar_campos_legados(plano) -> None:
    grupos = itens_por_categoria(plano)
    for categoria, _, campo in CATEGORIAS_PLANO:
        setattr(plano, campo, "\n".join(rel.item.texto for rel in grupos[categoria]) or None)


def sincronizar_rotacoes_legadas(plano) -> None:
    linhas = []
    for grupo, entradas in rotacoes_por_grupo(plano).items():
        nomes = [entrada.jogador.nome for entrada in entradas if entrada.jogador]
        if nomes:
            minuto = getattr(plano, f"rotacao_{grupo}_minuto", None)
            etiqueta = f"Cinco {grupo} (min {minuto})" if minuto is not None else f"Cinco {grupo}"
            linhas.append(etiqueta + ": " + " · ".join(nomes))
    plano.rotacoes = "\n".join(linhas) or None


def jogadas_disponiveis(db: Session, equipa_id: int):
    return db.query(SetPlay).join(Playbook, SetPlay.playbook_id == Playbook.id).filter(
        Playbook.equipa_id == equipa_id,
    ).order_by(SetPlay.categoria, SetPlay.ordem, SetPlay.nome).all()


def preview_jogada(setplay) -> str | None:
    passo = next(iter(setplay.passos), None)
    if not passo:
        return None
    if passo.imagem_coach:
        return normalizar_data_uri(passo.imagem_coach)
    desenho = decompor_desenho_editavel(passo.desenho)[0] if passo.desenho else None
    campo = Path(STATIC_DIR) / "campos" / "campo_meio.png"
    if desenho and campo.is_file():
        return compor_desenho_sobre_campo(campo, desenho)
    return desenho


def graficos_plano(plano) -> list[dict]:
    graficos = []
    campo = Path(STATIC_DIR) / "campos" / "campo_meio.png"
    for relacao in (plano.jogadas if plano else []):
        for indice, passo in enumerate(relacao.setplay.passos, start=1):
            desenho = decompor_desenho_editavel(passo.desenho)[0] if passo.desenho else None
            imagem = normalizar_data_uri(passo.imagem_coach) if passo.imagem_coach else None
            if desenho and campo.is_file():
                imagem = compor_desenho_sobre_campo(campo, desenho)
            graficos.append({
                "titulo": relacao.setplay.nome,
                "passo": indice,
                "observacao": (passo.observacao or relacao.setplay.descricao or "").strip(),
                "imagem": imagem,
            })
    return graficos

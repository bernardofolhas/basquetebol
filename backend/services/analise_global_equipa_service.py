"""Agregados do mapa global de análise de uma equipa."""

from collections import defaultdict

from sqlalchemy.orm import Session, selectinload

from models.assiduidade import RegistoAssiduidade
from models.jogo import Jogo
from models.planeamento import Macrociclo, Mesociclo, Microciclo, SessaoTreino
from models.treino import PlanoTreino
from services.conteudos_sessao_service import CATEGORIAS_POR_CODIGO
from services.estatistica_service import box_score_eventos


_CATEGORIAS_EXERCICIO = {
    "TIO": "tecnica_individual_ofensiva",
    "TID": "tecnica_individual_defensiva",
    "TAIO": "tatica_individual_ofensiva",
    "TAID": "tatica_individual_defensiva",
    "TCO": "tatica_coletiva_ofensiva",
    "TCD": "tatica_coletiva_defensiva",
    "FIS": "capacidades_motoras",
    "FÍS": "capacidades_motoras",
    "PSI": "psicologia",
}


def _codigo_categoria(valor: str | None) -> str | None:
    if not valor:
        return None
    normalizado = valor.strip().upper().replace("Á", "A").replace("Í", "I")
    return _CATEGORIAS_EXERCICIO.get(normalizado)


def _percentagem(parte: float, total: float) -> float:
    return round((parte / total) * 100, 1) if total else 0


def construir_analise_global_equipa(db: Session, equipa, jogadores: list) -> dict:
    """Reúne numa só leitura os indicadores usados pelas cinco áreas do mapa."""
    sessoes = db.query(SessaoTreino).options(
        selectinload(SessaoTreino.conteudos),
        selectinload(SessaoTreino.plano_treino).selectinload(PlanoTreino.exercicios),
    ).join(Microciclo).join(Mesociclo).join(Macrociclo).filter(
        Macrociclo.equipa_id == equipa.id,
        SessaoTreino.ativa.is_(True),
        SessaoTreino.e_jogo.is_(False),
    ).order_by(SessaoTreino.data.desc(), SessaoTreino.hora_inicio.desc()).all()
    sessao_ids = [sessao.id for sessao in sessoes]

    registos = []
    if sessao_ids:
        registos = db.query(RegistoAssiduidade).filter(
            RegistoAssiduidade.sessao_id.in_(sessao_ids)
        ).all()

    jogos = db.query(Jogo).options(
        selectinload(Jogo.convocados),
        selectinload(Jogo.eventos_estatistica),
    ).filter(Jogo.equipa_id == equipa.id).order_by(Jogo.data.desc(), Jogo.id.desc()).all()

    minutos_categoria = defaultdict(int)
    exercicios_agregados = {}
    total_exercicios = 0
    for sessao in sessoes:
        exercicios = sessao.plano_treino.exercicios if sessao.plano_treino else []
        for exercicio in exercicios:
            minutos = max(0, exercicio.minutos or 0)
            categoria = _codigo_categoria(exercicio.categoria)
            if categoria:
                minutos_categoria[categoria] += minutos
            nome = (exercicio.nome or "Exercício sem título").strip()
            chave = (nome.casefold(), categoria or (exercicio.categoria or "").strip())
            linha = exercicios_agregados.setdefault(chave, {
                "nome": nome,
                "categoria": categoria,
                "categoria_original": exercicio.categoria,
                "minutos": 0,
                "utilizacoes": 0,
            })
            linha["minutos"] += minutos
            linha["utilizacoes"] += 1
            total_exercicios += 1

    # Sessões ainda sem exercícios continuam representadas pelos conteúdos planeados.
    for sessao in sessoes:
        if sessao.plano_treino and sessao.plano_treino.exercicios:
            continue
        for conteudo in sessao.conteudos:
            if conteudo.categoria in CATEGORIAS_POR_CODIGO:
                minutos_categoria[conteudo.categoria] += max(0, conteudo.minutos or 0)

    total_minutos = sum(minutos_categoria.values())
    categorias = []
    for codigo, dados in CATEGORIAS_POR_CODIGO.items():
        minutos = minutos_categoria[codigo]
        categorias.append({
            "codigo": codigo,
            "sigla": dados["sigla"],
            "label": dados["label"],
            "minutos": minutos,
            "percentagem": _percentagem(minutos, total_minutos),
        })
    categorias.sort(key=lambda item: item["minutos"], reverse=True)

    exercicios = sorted(
        exercicios_agregados.values(),
        key=lambda item: (-item["minutos"], -item["utilizacoes"], item["nome"].casefold()),
    )
    for item in exercicios:
        dados = CATEGORIAS_POR_CODIGO.get(item["categoria"] or "", {})
        item["sigla"] = dados.get("sigla") or item["categoria_original"] or "—"
        item["media_minutos"] = round(item["minutos"] / item["utilizacoes"], 1)

    por_jogador = defaultdict(lambda: {"total": 0, "presencas": 0, "rpe": []})
    for registo in registos:
        linha = por_jogador[registo.jogador_id]
        linha["total"] += 1
        presente = bool(registo.presente) or registo.estado in {"presente", "limitado"}
        linha["presencas"] += int(presente)
        if registo.rpe_individual is not None:
            linha["rpe"].append(float(registo.rpe_individual))

    presencas_jogadores = []
    for jogador in jogadores:
        dados = por_jogador[jogador.id]
        rpe_medio = round(sum(dados["rpe"]) / len(dados["rpe"]), 1) if dados["rpe"] else None
        presencas_jogadores.append({
            "jogador": jogador,
            "presencas": dados["presencas"],
            "total": dados["total"],
            "taxa": _percentagem(dados["presencas"], dados["total"]),
            "rpe_medio": rpe_medio,
            "respostas_rpe": len(dados["rpe"]),
        })
    presencas_jogadores.sort(key=lambda item: (-item["taxa"], item["jogador"].nome.casefold()))
    total_registos = len(registos)
    total_presentes = sum(item["presencas"] for item in presencas_jogadores)
    valores_rpe = [float(item.rpe_individual) for item in registos if item.rpe_individual is not None]

    convocacoes_por_jogador = defaultdict(int)
    for jogo in jogos:
        for convocado in jogo.convocados:
            convocacoes_por_jogador[convocado.jogador_id] += 1
    convocatorias_jogadores = [{
        "jogador": jogador,
        "total": convocacoes_por_jogador[jogador.id],
        "percentagem": _percentagem(convocacoes_por_jogador[jogador.id], len(jogos)),
    } for jogador in jogadores]
    convocatorias_jogadores.sort(key=lambda item: (-item["total"], item["jogador"].nome.casefold()))
    jogos_com_convocatoria = [jogo for jogo in jogos if jogo.convocados]

    eventos = [
        evento for jogo in jogos for evento in jogo.eventos_estatistica
        if not evento.anulado
    ]
    box = box_score_eventos(eventos)
    totais_box = defaultdict(int)
    for linha in box.values():
        for chave in ("pts", "ro", "rd", "ast", "stl", "to", "blk", "pf"):
            totais_box[chave] += linha[chave]
    estatisticas_jogadores = []
    for jogador in jogadores:
        linha = box.get(jogador.id)
        if not linha:
            continue
        estatisticas_jogadores.append({"jogador": jogador, **linha})
    estatisticas_jogadores.sort(key=lambda item: (-item["pts"], -item["eff"], item["jogador"].nome.casefold()))
    jogos_com_estatisticas = {evento.jogo_id for evento in eventos}
    jogos_concluidos = [jogo for jogo in jogos if jogo.pontos_nos is not None and jogo.pontos_adversario is not None]
    vitorias = sum(jogo.pontos_nos > jogo.pontos_adversario for jogo in jogos_concluidos)

    return {
        "global": {
            "treinos": len(sessoes),
            "jogos": len(jogos),
            "atletas": len(jogadores),
            "minutos": total_minutos,
            "taxa_presenca": _percentagem(total_presentes, total_registos),
            "rpe_medio": round(sum(valores_rpe) / len(valores_rpe), 1) if valores_rpe else None,
            "vitorias": vitorias,
            "jogos_concluidos": len(jogos_concluidos),
        },
        "categorias": categorias,
        "exercicios": exercicios,
        "total_exercicios": total_exercicios,
        "presencas": {
            "jogadores": presencas_jogadores,
            "registos": total_registos,
            "presentes": total_presentes,
            "taxa": _percentagem(total_presentes, total_registos),
            "rpe_medio": round(sum(valores_rpe) / len(valores_rpe), 1) if valores_rpe else None,
            "respostas_rpe": len(valores_rpe),
        },
        "convocatorias": {
            "jogadores": convocatorias_jogadores,
            "jogos": jogos,
            "jogos_com_convocatoria": len(jogos_com_convocatoria),
            "total": sum(len(jogo.convocados) for jogo in jogos),
            "media": round(sum(len(jogo.convocados) for jogo in jogos_com_convocatoria) / len(jogos_com_convocatoria), 1) if jogos_com_convocatoria else 0,
        },
        "estatisticas": {
            "jogadores": estatisticas_jogadores,
            "jogos": jogos,
            "jogos_com_dados": len(jogos_com_estatisticas),
            "eventos": sum(evento.tipo != "minutos_oficiais" for evento in eventos),
            "totais": dict(totais_box),
            "vitorias": vitorias,
            "derrotas": len(jogos_concluidos) - vitorias,
            "jogos_concluidos": len(jogos_concluidos),
        },
    }

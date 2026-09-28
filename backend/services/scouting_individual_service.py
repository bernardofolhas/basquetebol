"""Leitura comum do perfil individual para Studio, cartões e exportações."""

from collections import defaultdict


AVALIACOES = {
    1: {"texto": "Muito fraco", "tom": "weak"},
    2: {"texto": "Fraco", "tom": "weak"},
    3: {"texto": "Médio", "tom": "average"},
    4: {"texto": "Forte", "tom": "strong"},
    5: {"texto": "Muito forte / elite", "tom": "strong"},
}


def avaliacao_meta(valor: int | None) -> dict:
    meta = AVALIACOES.get(valor, {"texto": "Não avaliado", "tom": "na"})
    return {
        "valor": valor,
        "texto": meta["texto"],
        "tom": meta["tom"],
        "segmentos": [bool(valor and indice <= valor) for indice in range(1, 6)],
    }


def _ordem(relacao):
    return (
        relacao.ordem_destaque if relacao.destaque and relacao.ordem_destaque is not None else 10_000,
        relacao.ordem or 0,
        relacao.item.ordem or 0,
        relacao.item.nome.casefold(),
    )


def construir_perfil_individual(jogador, apenas_destaques: bool = False) -> dict:
    """Normaliza a mesma informação para todos os consumidores do scouting."""
    relacoes = [rel for rel in (jogador.itens or []) if rel.item and rel.item.ativo]
    if apenas_destaques:
        relacoes = [rel for rel in relacoes if rel.destaque]

    grupos = defaultdict(list)
    tendencias = []
    game_plan = []
    legado = defaultdict(list)
    for relacao in sorted(relacoes, key=_ordem):
        categoria = relacao.item.categoria
        if categoria == "caracteristica":
            grupo = relacao.item.grupo
            chave = grupo.id if grupo else None
            grupos[chave].append(relacao)
        elif categoria in {"tendencia", "movimento"}:
            tendencias.append(relacao)
        elif categoria in {"game_plan", "estrategia"}:
            game_plan.append(relacao)
        else:
            legado[categoria].append(relacao)

    grupos_ordenados = []
    for relacoes_grupo in grupos.values():
        grupo = relacoes_grupo[0].item.grupo
        grupos_ordenados.append({
            "id": grupo.id if grupo else None,
            "nome": grupo.nome if grupo else "Perfil técnico",
            "ordem": grupo.ordem if grupo else 10_000,
            "itens": [
                {"relacao": rel, "avaliacao": avaliacao_meta(rel.avaliacao)}
                for rel in relacoes_grupo
            ],
        })
    grupos_ordenados.sort(key=lambda grupo: (grupo["ordem"], grupo["nome"].casefold()))
    avaliacoes = [entrada for grupo in grupos_ordenados for entrada in grupo["itens"]]
    return {
        "grupos": grupos_ordenados,
        "avaliacoes": avaliacoes,
        "tendencias": tendencias,
        "game_plan": game_plan,
        "legado": dict(legado),
    }

from models.avaliacao import AvaliacaoJogador


CATEGORIAS_AVALIACAO = {
    "tecnica": "Técnica",
    "tatica": "Tática",
    "psicologica": "Psicológica",
    "fisica": "Física",
}


def dados_dashboard_avaliacoes(avaliacoes: list[AvaliacaoJogador]) -> list[dict]:
    """Serializa os registos necessários aos filtros e gráficos no browser."""
    dados = []
    for item in avaliacoes:
        parametro = item.parametro
        minimo = float(parametro.valor_minimo or 0)
        maximo = float(parametro.valor_maximo or 5)
        intervalo = maximo - minimo
        normalizado = ((float(item.valor) - minimo) / intervalo * 100) if intervalo > 0 else 0
        dados.append({
            "id": item.id,
            "data": item.data.isoformat(),
            "jogador_id": item.jogador_id,
            "jogador": item.jogador.nome if item.jogador else "Atleta",
            "parametro_id": item.parametro_id,
            "parametro": parametro.nome,
            "categoria": parametro.categoria,
            "categoria_label": CATEGORIAS_AVALIACAO.get(
                parametro.categoria, parametro.categoria.title()
            ),
            "valor": float(item.valor),
            "minimo": minimo,
            "maximo": maximo,
            "unidade": parametro.unidade or ("/5" if parametro.categoria != "fisica" else ""),
            "normalizado": round(max(0, min(100, normalizado)), 2),
            "sessao_id": item.sessao_id,
            "sessao": (
                f"Treino {item.sessao.numero_treino}"
                if item.sessao and item.sessao.numero_treino
                else ("Treino" if item.sessao else "Avaliação livre")
            ),
        })
    return dados

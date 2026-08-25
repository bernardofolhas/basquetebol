"""Regras para os conteúdos distribuídos pelos treinos do microciclo."""

from datetime import date

CATEGORIAS_CONTEUDO_SESSAO = (
    ("tecnica_individual_ofensiva", "Técnica individual ofensiva", "TIO", "min_tecnica_individual_ofensiva"),
    ("tecnica_individual_defensiva", "Técnica individual defensiva", "TID", "min_tecnica_individual_defensiva"),
    ("tatica_individual_ofensiva", "Tática individual ofensiva", "TaIO", "min_tatica_individual_ofensiva"),
    ("tatica_individual_defensiva", "Tática individual defensiva", "TaID", "min_tatica_individual_defensiva"),
    ("tatica_coletiva_ofensiva", "Tática coletiva ofensiva", "TCO", "min_tatica_coletiva_ofensiva"),
    ("tatica_coletiva_defensiva", "Tática coletiva defensiva", "TCD", "min_tatica_coletiva_defensiva"),
    ("capacidades_motoras", "Capacidades motoras", "FÍS", "min_fisicos"),
    ("psicologia", "Psicologia", "PSI", "min_psicologicos"),
)

CATEGORIAS_POR_CODIGO = {
    codigo: {"label": label, "sigla": sigla, "campo_minutos": campo}
    for codigo, label, sigla, campo in CATEGORIAS_CONTEUDO_SESSAO
}

NOMES_DIAS_SEMANA = (
    "Segunda-feira",
    "Terça-feira",
    "Quarta-feira",
    "Quinta-feira",
    "Sexta-feira",
    "Sábado",
    "Domingo",
)


def categorias_conteudo_para_ui() -> list[dict[str, str]]:
    return [
        {"codigo": codigo, "label": label, "sigla": sigla}
        for codigo, label, sigla, _ in CATEGORIAS_CONTEUDO_SESSAO
    ]


def atualizar_minutos_por_componente(sessao) -> None:
    """Recalcula os totais do quadro de balanço a partir dos conteúdos guardados."""
    totais = {codigo: 0 for codigo, *_ in CATEGORIAS_CONTEUDO_SESSAO}
    for conteudo in sessao.conteudos:
        if conteudo.categoria in totais:
            totais[conteudo.categoria] += conteudo.minutos or 0

    for codigo, dados in CATEGORIAS_POR_CODIGO.items():
        setattr(sessao, dados["campo_minutos"], totais[codigo])


def calcular_balanco_minutos(sessao, ignorar_conteudo_id: int | None = None) -> dict[str, int | None]:
    """Resume os minutos distribuídos e o limite definido para o treino."""
    atribuidos = sum(
        conteudo.minutos or 0
        for conteudo in sessao.conteudos
        if ignorar_conteudo_id is None or getattr(conteudo, "id", None) != ignorar_conteudo_id
    )
    limite = getattr(sessao, "volume_minutos", None)
    return {
        "atribuidos": atribuidos,
        "limite": limite,
        "disponiveis": max(0, limite - atribuidos) if limite is not None else None,
    }


def construir_visao_semanal_conteudos(
    sessoes: list,
) -> list[dict]:
    """Prepara a grelha: apenas treinos previstos nas colunas."""
    treinos = []
    for sessao in sorted(
        sessoes,
        key=lambda item: (item.data, getattr(item, "hora_inicio", None) or "", item.id or 0),
    ):
        conteudos_por_categoria = {codigo: [] for codigo in CATEGORIAS_POR_CODIGO}
        for conteudo in sessao.conteudos:
            if conteudo.categoria in conteudos_por_categoria:
                conteudos_por_categoria[conteudo.categoria].append({
                    "id": getattr(conteudo, "id", None),
                    "descricao": conteudo.descricao,
                    "minutos": conteudo.minutos,
                })
        balanco_minutos = calcular_balanco_minutos(sessao)
        treinos.append({
            "sessao_id": sessao.id,
            "numero_treino": sessao.numero_treino,
            "tipo_treino": getattr(sessao, "tipo_treino", None) or "normal",
            "titulo_treino": (
                f"Treino físico {sessao.numero_treino}"
                if (getattr(sessao, "tipo_treino", None) or "normal") == "fisico"
                else f"Treino {sessao.numero_treino}"
            ),
            "data": sessao.data,
            "dia_semana": NOMES_DIAS_SEMANA[sessao.data.weekday()],
            "hora_inicio": getattr(sessao, "hora_inicio", None),
            "hora_fim": getattr(sessao, "hora_fim", None),
            "local": getattr(sessao, "local", None),
            "minutos_atribuidos": balanco_minutos["atribuidos"],
            "minutos_limite": balanco_minutos["limite"],
            "minutos_disponiveis": balanco_minutos["disponiveis"],
            "conteudos_por_categoria": conteudos_por_categoria,
        })
    return treinos

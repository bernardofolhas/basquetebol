"""Regras para os conteúdos distribuídos pelos treinos do microciclo."""

from datetime import date, timedelta

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


def construir_visao_semanal_conteudos(
    data_inicio: date,
    data_fim: date,
    sessoes: list,
) -> list[dict]:
    """Prepara a grelha semanal: dias nas colunas e componentes nas linhas."""
    sessoes_por_data: dict[date, list] = {}
    for sessao in sessoes:
        sessoes_por_data.setdefault(sessao.data, []).append(sessao)

    dias = []
    data_atual = data_inicio
    while data_atual <= data_fim:
        conteudos_por_categoria = {codigo: [] for codigo in CATEGORIAS_POR_CODIGO}
        treinos = sessoes_por_data.get(data_atual, [])
        for sessao in treinos:
            for conteudo in sessao.conteudos:
                if conteudo.categoria in conteudos_por_categoria:
                    conteudos_por_categoria[conteudo.categoria].append({
                        "sessao_id": sessao.id,
                        "treino_numero": sessao.numero_treino,
                        "descricao": conteudo.descricao,
                        "minutos": conteudo.minutos,
                    })
        dias.append({
            "data": data_atual,
            "dia_semana": NOMES_DIAS_SEMANA[data_atual.weekday()],
            "treinos": treinos,
            "conteudos_por_categoria": conteudos_por_categoria,
        })
        data_atual += timedelta(days=1)
    return dias

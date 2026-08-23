"""Regras para os conteúdos distribuídos pelos treinos do microciclo."""

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

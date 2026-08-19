"""Dados de apresentação partilhados pelo mapa e PDF de atribuição de espaços."""

from datetime import timedelta


# Tons suaves com texto escuro: distinguem equipas sem perder legibilidade.
PALETA_EQUIPAS = (
    {"marca": "#0f766e", "fundo": "#ccfbf1", "borda": "#5eead4", "texto": "#134e4a"},
    {"marca": "#1d4ed8", "fundo": "#dbeafe", "borda": "#93c5fd", "texto": "#1e3a8a"},
    {"marca": "#be123c", "fundo": "#ffe4e6", "borda": "#fda4af", "texto": "#881337"},
    {"marca": "#7e22ce", "fundo": "#f3e8ff", "borda": "#d8b4fe", "texto": "#581c87"},
    {"marca": "#b45309", "fundo": "#fef3c7", "borda": "#fcd34d", "texto": "#78350f"},
    {"marca": "#0e7490", "fundo": "#cffafe", "borda": "#67e8f9", "texto": "#164e63"},
    {"marca": "#9f1239", "fundo": "#fce7f3", "borda": "#f9a8d4", "texto": "#831843"},
    {"marca": "#4d7c0f", "fundo": "#ecfccb", "borda": "#bef264", "texto": "#365314"},
    {"marca": "#4338ca", "fundo": "#e0e7ff", "borda": "#a5b4fc", "texto": "#312e81"},
    {"marca": "#c2410c", "fundo": "#ffedd5", "borda": "#fdba74", "texto": "#7c2d12"},
)
COR_NEUTRA = {"marca": "#475569", "fundo": "#f1f5f9", "borda": "#cbd5e1", "texto": "#334155"}


def cor_equipa(equipa_id: int | None) -> dict[str, str]:
    """Devolve uma cor determinística, visualmente aleatória, para cada equipa."""
    if not equipa_id:
        return COR_NEUTRA
    indice = (int(equipa_id) * 7 + 3) % len(PALETA_EQUIPAS)
    return PALETA_EQUIPAS[indice]


def construir_cores_equipas(equipas) -> dict[int, dict[str, str]]:
    return {equipa.id: cor_equipa(equipa.id) for equipa in equipas}


def construir_quadro_atribuicoes(semanal, equipas, atribuicoes) -> dict:
    """Organiza reservas numa matriz fixa: uma linha por equipa e um dia por coluna."""
    total_dias = (semanal.data_fim - semanal.data_inicio).days + 1
    dias = [semanal.data_inicio + timedelta(days=deslocamento) for deslocamento in range(total_dias)]
    por_equipa_dia: dict[tuple[int, object], list] = {}

    for atribuicao in atribuicoes:
        if not atribuicao.equipa_id:
            continue
        chave = (atribuicao.equipa_id, atribuicao.data)
        por_equipa_dia.setdefault(chave, []).append(atribuicao)

    linhas = []
    for equipa in sorted(equipas, key=lambda item: item.nome.casefold()):
        celulas = []
        for dia in dias:
            reservas = sorted(
                por_equipa_dia.get((equipa.id, dia), []),
                key=lambda item: (item.hora_inicio, item.hora_fim, item.espaco.nome.casefold()),
            )
            celulas.append({
                "dia": dia,
                "reservas": reservas,
            })
        linhas.append({"equipa": equipa, "cor": cor_equipa(equipa.id), "celulas": celulas})

    return {"dias": dias, "linhas": linhas}

"""Apresentação consistente dos objetivos por categoria entre níveis."""


CATEGORIAS_OBJETIVOS = (
    ("Objetivos Gerais", "objetivos_gerais"),
    ("Ofensivos", "objetivos_ofensivos"),
    ("Defensivos", "objetivos_defensivos"),
    ("Psicológicos", "obj_psicologicos"),
    ("Físicos", "obj_fisicos"),
)


def objetivos_por_categoria(objeto) -> list[dict[str, str]]:
    # Mantém dados antigos visíveis enquanto a plataforma usa as categorias
    # simplificadas nos novos formulários.
    valores = {
        "objetivos_gerais": getattr(objeto, "objetivos_gerais", None),
        "objetivos_ofensivos": getattr(objeto, "objetivos_ofensivos", None) or "\n".join(
            filtro for filtro in (
                getattr(objeto, "obj_tecnica_individual_ofensiva", None),
                getattr(objeto, "obj_tatica_individual_ofensiva", None),
                getattr(objeto, "obj_tatica_coletiva_ofensiva", None),
            ) if filtro
        ) or None,
        "objetivos_defensivos": getattr(objeto, "objetivos_defensivos", None) or "\n".join(
            filtro for filtro in (
                getattr(objeto, "obj_tecnica_individual_defensiva", None),
                getattr(objeto, "obj_tatica_individual_defensiva", None),
                getattr(objeto, "obj_tatica_coletiva_defensiva", None),
            ) if filtro
        ) or None,
        "obj_psicologicos": getattr(objeto, "obj_psicologicos", None),
        "obj_fisicos": getattr(objeto, "obj_fisicos", None),
    }
    return [
        {"label": label, "campo": campo, "texto": valores.get(campo)}
        for label, campo in CATEGORIAS_OBJETIVOS
        if valores.get(campo)
    ]


def contexto_objetivos_superiores(*, macrociclo=None, mesociclo=None) -> dict[str, list[dict[str, str]]]:
    return {
        "macrociclo": objetivos_por_categoria(macrociclo) if macrociclo else [],
        "mesociclo": objetivos_por_categoria(mesociclo) if mesociclo else [],
    }

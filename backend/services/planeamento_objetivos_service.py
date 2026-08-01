"""Apresentação consistente dos objetivos por categoria entre níveis."""


CATEGORIAS_OBJETIVOS = (
    ("Tecnica individual ofensiva", "obj_tecnica_individual_ofensiva"),
    ("Tecnica individual defensiva", "obj_tecnica_individual_defensiva"),
    ("Tatica individual ofensiva", "obj_tatica_individual_ofensiva"),
    ("Tatica individual defensiva", "obj_tatica_individual_defensiva"),
    ("Tatica coletiva ofensiva", "obj_tatica_coletiva_ofensiva"),
    ("Tatica coletiva defensiva", "obj_tatica_coletiva_defensiva"),
    ("Fisicos", "obj_fisicos"),
    ("Psicologicos", "obj_psicologicos"),
)


def objetivos_por_categoria(objeto) -> list[dict[str, str]]:
    return [
        {"label": label, "campo": campo, "texto": getattr(objeto, campo, None)}
        for label, campo in CATEGORIAS_OBJETIVOS
        if getattr(objeto, campo, None)
    ]


def contexto_objetivos_superiores(*, macrociclo=None, mesociclo=None) -> dict[str, list[dict[str, str]]]:
    return {
        "macrociclo": objetivos_por_categoria(macrociclo) if macrociclo else [],
        "mesociclo": objetivos_por_categoria(mesociclo) if mesociclo else [],
    }

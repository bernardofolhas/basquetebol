"""Vocabulário apresentado conforme o contexto da equipa."""


def termo_jogador(equipa=None, plural: bool = False, capitalizar: bool = True) -> str:
    """Devolve Jogador/Jogadora conforme o género; sem equipa usa Atleta."""
    genero = getattr(equipa, "genero", None)
    valor_genero = getattr(genero, "value", genero)
    valor_normalizado = str(valor_genero or "").strip().casefold()

    if valor_normalizado == "masculino":
        termo = "jogadores" if plural else "jogador"
    elif valor_normalizado == "feminino":
        termo = "jogadoras" if plural else "jogadora"
    else:
        termo = "atletas" if plural else "atleta"
    return termo.capitalize() if capitalizar else termo

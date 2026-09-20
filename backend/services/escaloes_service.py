"""Regras comuns de progressão competitiva entre escalões."""

from models.equipa import EscalaoEnum


# A chamada é sempre para o escalão imediatamente inferior na hierarquia
# competitiva definida para esta funcionalidade.
HIERARQUIA_ESCALOES = (
    EscalaoEnum.sub14,
    EscalaoEnum.sub16,
    EscalaoEnum.sub18,
    EscalaoEnum.sub23,
    EscalaoEnum.senior,
)


def escalao_imediatamente_inferior(escalao):
    """Devolve o único escalão elegível para uma chamada temporária."""
    try:
        indice = HIERARQUIA_ESCALOES.index(escalao)
    except ValueError:
        return None
    return HIERARQUIA_ESCALOES[indice - 1] if indice else None

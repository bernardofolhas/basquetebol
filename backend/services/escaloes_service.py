"""Regras comuns de progressão competitiva entre escalões."""

import re
import unicodedata

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


def _normalizar_designacao(valor: str) -> str:
    texto = unicodedata.normalize("NFKD", valor or "")
    return re.sub(r"[^a-z0-9]", "", texto.encode("ascii", "ignore").decode().lower())


def escalao_imediatamente_inferior_da_equipa(equipa):
    """Resolve também equipas antigas cujo nome e escalão guardado não coincidem."""
    nome_normalizado = _normalizar_designacao(getattr(equipa, "nome", ""))
    escalao_atual = getattr(equipa, "escalao", None)
    for escalao in HIERARQUIA_ESCALOES:
        if _normalizar_designacao(escalao.value) in nome_normalizado:
            escalao_atual = escalao
            break
    return escalao_imediatamente_inferior(escalao_atual)

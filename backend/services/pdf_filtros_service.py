"""Filtros opcionais e reutilizaveis para exportacoes PDF."""

from __future__ import annotations

from collections.abc import Iterable
import unicodedata


TIPOS_AGENDA_PDF = frozenset({"treino", "jogo", "atividade"})


def _ativo(valor: str | None, padrao: bool = True) -> bool:
    if valor is None:
        return padrao
    return valor.strip().lower() not in {"0", "false", "nao", "não", "off"}


def obter_filtros_pdf(request) -> dict:
    """Normaliza filtros vindos da query string, mantendo tudo por defeito."""
    query = getattr(request, "query_params", {})
    tipos_recebidos = {
        tipo.strip().lower()
        for tipo in query.get("pdf_tipos", "").split(",")
        if tipo.strip().lower() in TIPOS_AGENDA_PDF
    }
    return {
        "tipos": tipos_recebidos or set(TIPOS_AGENDA_PDF),
        "casa": _ativo(query.get("pdf_casa")),
        "fora": _ativo(query.get("pdf_fora")),
        "competicao": query.get("pdf_competicao", "").strip(),
        "observacoes": _ativo(query.get("pdf_observacoes")),
        "indicadores": _ativo(query.get("pdf_indicadores")),
        "imagens": _ativo(query.get("pdf_imagens")),
    }


def grupo_categoria_agenda(categoria: str | None) -> str:
    categoria = (categoria or "").strip().lower()
    if categoria in {"treino", "fisico", "treino_fisico"}:
        return "treino"
    if categoria == "jogo":
        return "jogo"
    return "atividade"


def filtrar_itens_agenda(itens: Iterable[dict], filtros: dict) -> list[dict]:
    tipos = filtros.get("tipos") or TIPOS_AGENDA_PDF
    return [item for item in itens if grupo_categoria_agenda(item.get("categoria")) in tipos]


def filtrar_jogos(jogos: Iterable, filtros: dict) -> list:
    """Filtra casa/fora e competicao sem depender de um modelo concreto."""
    def normalizar(valor: str) -> str:
        return "".join(
            caractere for caractere in unicodedata.normalize("NFKD", valor.casefold())
            if not unicodedata.combining(caractere)
        )

    termo = normalizar(filtros.get("competicao") or "")
    if termo in {"amigavel", "amigaveis"}:
        termo = "amigavel"
    resultado = []
    for jogo in jogos:
        em_casa = bool(getattr(jogo, "em_casa", False))
        if em_casa and not filtros.get("casa", True):
            continue
        if not em_casa and not filtros.get("fora", True):
            continue
        if termo and termo not in normalizar(getattr(jogo, "competicao", None) or ""):
            continue
        resultado.append(jogo)
    return resultado

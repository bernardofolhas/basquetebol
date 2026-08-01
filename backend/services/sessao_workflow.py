"""Estados operacionais e transições do ciclo de vida de uma sessão."""

ESTADOS_SESSAO = (
    "planeada",
    "confirmada",
    "executada",
    "registada",
    "revista",
    "cancelada",
)

ROTULOS_ESTADO_SESSAO = {
    "planeada": "Planeada",
    "confirmada": "Confirmada",
    "executada": "Executada",
    "registada": "Registada",
    "revista": "Revista",
    "cancelada": "Cancelada",
}

CLASSES_ESTADO_SESSAO = {
    "planeada": "bg-slate-100 text-slate-700",
    "confirmada": "bg-blue-100 text-blue-800",
    "executada": "bg-amber-100 text-amber-800",
    "registada": "bg-violet-100 text-violet-800",
    "revista": "bg-emerald-100 text-emerald-800",
    "cancelada": "bg-red-100 text-red-800",
}

# Permite avancar, corrigir uma etapa e reabrir uma sessao cancelada sem
# transformar a rota num CRUD livre de estados incoerentes.
TRANSICOES_SESSAO = {
    "planeada": {"confirmada", "cancelada"},
    "confirmada": {"planeada", "executada", "cancelada"},
    "executada": {"confirmada", "registada"},
    "registada": {"executada", "revista"},
    "revista": {"registada"},
    "cancelada": {"planeada"},
}


def normalizar_estado_sessao(estado: str | None) -> str:
    """Devolve um estado valido, tratando linhas antigas sem coluna preenchida."""
    valor = (estado or "planeada").strip().lower()
    return valor if valor in ESTADOS_SESSAO else "planeada"


def estado_sessao_visual(estado: str | None) -> dict[str, str]:
    """Prepara o estado para badges e tabelas de interface."""
    codigo = normalizar_estado_sessao(estado)
    return {
        "codigo": codigo,
        "label": ROTULOS_ESTADO_SESSAO[codigo],
        "classes": CLASSES_ESTADO_SESSAO[codigo],
    }


def transicao_sessao_valida(estado_atual: str | None, novo_estado: str | None) -> bool:
    """Indica se a alteracao pedida respeita o fluxo operacional."""
    atual = normalizar_estado_sessao(estado_atual)
    novo = (novo_estado or "").strip().lower()
    return novo in TRANSICOES_SESSAO.get(atual, set())


def proxima_acao_sessao(estado: str | None) -> str:
    """Texto curto para orientar a proxima tarefa do treinador."""
    return {
        "planeada": "Preparar sessão",
        "confirmada": "Abrir sessão",
        "executada": "Registar sessão",
        "registada": "Rever sessão",
        "revista": "Sessão concluída",
        "cancelada": "Reativar sessão",
    }[normalizar_estado_sessao(estado)]


def opcoes_transicao_sessao(estado: str | None) -> list[dict[str, str]]:
    """Devolve apenas os estados permitidos a partir do estado atual."""
    atual = normalizar_estado_sessao(estado)
    return [
        {"codigo": codigo, "label": ROTULOS_ESTADO_SESSAO[codigo]}
        for codigo in sorted(TRANSICOES_SESSAO.get(atual, set()))
    ]

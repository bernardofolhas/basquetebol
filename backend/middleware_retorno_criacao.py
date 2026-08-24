"""Mantém o utilizador no contexto onde iniciou uma ação."""

from urllib.parse import urlsplit

from starlette.middleware.base import BaseHTTPMiddleware


FORMULARIOS = ("/novo", "/nova", "/criar", "/editar")
MARCADORES_FORMULARIO = ("/disponibilidades", "/indisponibilidades", "/blocos")
PREFIXOS_EXCLUIDOS = (
    "/login-form",
    "/logout",
    "/recuperar-password",
    "/redefinir-password",
    "/acesso-temporario",
    "/minha-conta/alterar-password",
    "/notificacoes",
)
CABECALHO_DESTINO_PROTEGIDO = "x-context-redirect-locked"


def _caminho_interno(valor: str | None, caminho_atual: str = "") -> str | None:
    """Converte um URL de referência num destino interno sem permitir open redirect."""
    if not valor:
        return None
    partes = urlsplit(valor)
    caminho = partes.path
    if not caminho.startswith("/") or caminho.startswith("//") or caminho == caminho_atual:
        return None
    return caminho + (f"?{partes.query}" if partes.query else "")


def _e_formulario(caminho: str) -> bool:
    return caminho.endswith(FORMULARIOS) or any(marcador in caminho for marcador in MARCADORES_FORMULARIO)


def _e_criacao(caminho: str) -> bool:
    """Compatibilidade com testes e chamadas antigas."""
    return caminho.endswith(("/novo", "/nova", "/criar")) or any(
        marcador in caminho for marcador in MARCADORES_FORMULARIO
    )


def _abre_dashboard_criado(caminho: str) -> bool:
    """Mantido por compatibilidade; todas as ações regressam agora à origem."""
    return False


def _e_acao_excluida(caminho: str) -> bool:
    if caminho.startswith(PREFIXOS_EXCLUIDOS):
        return True
    return caminho == "/superadmin/sair-suporte" or (
        caminho.startswith("/superadmin/clubes/") and caminho.endswith("/entrar")
    )


class RetornoAposCriacaoMiddleware(BaseHTTPMiddleware):
    """Uniformiza o retorno após criar, editar, eliminar ou confirmar ações."""

    async def dispatch(self, request, call_next):
        caminho = request.url.path
        chave = f"retorno_acao:{caminho}"

        if request.method == "GET" and _e_formulario(caminho) and not _e_acao_excluida(caminho):
            origem = _caminho_interno(request.query_params.get("retorno"), caminho)
            origem = origem or _caminho_interno(request.headers.get("referer"), caminho)
            if origem:
                request.session[chave] = origem

        response = await call_next(request)

        if (
            request.method not in {"POST", "PUT", "PATCH", "DELETE"}
            or _e_acao_excluida(caminho)
            or response.status_code not in {302, 303}
            or response.headers.get(CABECALHO_DESTINO_PROTEGIDO) == "1"
        ):
            return response

        destino_original = _caminho_interno(response.headers.get("location"))
        # Em validações inválidas, o router regressa ao formulário; não se perde o erro.
        if destino_original == caminho:
            return response

        destino = request.session.pop(chave, None)
        destino = destino or _caminho_interno(request.headers.get("referer"), caminho)
        if destino:
            response.headers["location"] = destino
        return response

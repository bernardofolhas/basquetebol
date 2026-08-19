"""Mantém o utilizador no contexto de onde iniciou uma criação."""

from urllib.parse import urlsplit

from starlette.middleware.base import BaseHTTPMiddleware


def _caminho_interno(valor: str | None, caminho_atual: str = "") -> str | None:
    if not valor:
        return None
    partes = urlsplit(valor)
    caminho = partes.path
    if not caminho.startswith("/") or caminho.startswith("//") or caminho == caminho_atual:
        return None
    return caminho + (f"?{partes.query}" if partes.query else "")


def _e_criacao(caminho: str) -> bool:
    return caminho.endswith(("/novo", "/nova", "/criar")) or any(
        marcador in caminho for marcador in ("/disponibilidades", "/indisponibilidades", "/blocos")
    )


def _abre_dashboard_criado(caminho: str) -> bool:
    return any(marcador in caminho for marcador in (
        "/macrociclos/novo",
        "/mesociclos/novo",
        "/microciclos/novo",
    ))


class RetornoAposCriacaoMiddleware(BaseHTTPMiddleware):
    """Substitui apenas o destino de criações bem-sucedidas pelo contexto anterior."""

    async def dispatch(self, request, call_next):
        caminho = request.url.path
        chave = f"retorno_criacao:{caminho}"

        if request.method == "GET" and _e_criacao(caminho) and not _abre_dashboard_criado(caminho):
            origem = _caminho_interno(request.query_params.get("retorno"), caminho)
            origem = origem or _caminho_interno(request.headers.get("referer"), caminho)
            if origem:
                request.session[chave] = origem

        response = await call_next(request)

        if (
            request.method != "POST"
            or not _e_criacao(caminho)
            or _abre_dashboard_criado(caminho)
            or response.status_code not in {302, 303}
        ):
            return response

        destino_original = response.headers.get("location", "")
        # Em validações inválidas, o router regressa ao formulário; não se perde o erro.
        if _caminho_interno(destino_original) == caminho:
            return response

        destino = request.session.pop(chave, None)
        destino = destino or _caminho_interno(request.headers.get("referer"), caminho)
        if destino:
            response.headers["location"] = destino
        return response

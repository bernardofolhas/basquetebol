"""Evita que páginas operacionais mostrem dados antigos após uma alteração."""

from starlette.middleware.base import BaseHTTPMiddleware


class PaginasDinamicasSemCacheMiddleware(BaseHTTPMiddleware):
    """Desativa cache apenas para HTML dinâmico, sem afetar PDFs ou estáticos."""

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        content_type = response.headers.get("content-type", "")
        if content_type.startswith("text/html"):
            response.headers["Cache-Control"] = "private, no-store, max-age=0, must-revalidate"
            response.headers["Pragma"] = "no-cache"
        return response

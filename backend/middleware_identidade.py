from starlette.middleware.base import BaseHTTPMiddleware

from database import SessionLocal
from services.identidade_clube_service import obter_identidade_clube


class IdentidadeClubeMiddleware(BaseHTTPMiddleware):
    """Disponibiliza a identidade visual em todas as páginas sem duplicar contexto."""

    async def dispatch(self, request, call_next):
        if request.url.path.startswith("/static"):
            return await call_next(request)

        db = SessionLocal()
        try:
            request.state.identidade_clube = obter_identidade_clube(db)
        except Exception:
            request.state.identidade_clube = None
        finally:
            db.close()
        return await call_next(request)

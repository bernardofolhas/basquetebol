"""Disponibiliza navegação operacional em todas as páginas autenticadas."""

from starlette.middleware.base import BaseHTTPMiddleware

from auth import obter_utilizador_atual
from database import SessionLocal
from services.navegacao_service import obter_contexto_navegacao


class NavegacaoGlobalMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        request.state.navegacao = None
        if request.url.path.startswith("/static"):
            return await call_next(request)

        db = SessionLocal()
        try:
            utilizador = obter_utilizador_atual(request, db)
            if utilizador:
                request.state.navegacao = obter_contexto_navegacao(
                    db,
                    utilizador,
                    getattr(request.state, "clube_atual", None),
                )
        except Exception:
            request.state.navegacao = None
        finally:
            db.close()
        return await call_next(request)

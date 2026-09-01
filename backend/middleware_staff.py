"""Restrições transversais das contas de staff."""

import re

from fastapi.responses import JSONResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware

from auth import obter_utilizador_atual
from database import SessionLocal


class StaffPermissionsMiddleware(BaseHTTPMiddleware):
    """Impede alterações técnicas fora do âmbito atribuído ao staff."""

    async def dispatch(self, request, call_next):
        caminho = request.url.path
        if caminho.startswith("/static"):
            return await call_next(request)

        db = SessionLocal()
        try:
            utilizador = obter_utilizador_atual(request, db)
            if not utilizador or utilizador.perfil.value != "staff":
                return await call_next(request)

            bloqueado = (
                caminho.startswith("/scouting")
                or bool(re.match(r"^/jogos/\d+/plano(?:/|$)", caminho))
                or (
                    request.method not in {"GET", "HEAD", "OPTIONS"}
                    and caminho.startswith(("/planeamento", "/treino", "/agenda"))
                )
            )
            if not bloqueado:
                return await call_next(request)

            if request.headers.get("accept", "").startswith("application/json") or request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JSONResponse(status_code=403, content={"detail": "Esta conta de staff não pode alterar esta área."})
            return RedirectResponse(url="/dashboard", status_code=303)
        finally:
            db.close()

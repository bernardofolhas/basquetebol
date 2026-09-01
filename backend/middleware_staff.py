"""Restrições transversais das contas de staff."""

import re

from fastapi.responses import JSONResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware

from auth import obter_utilizador_atual
from database import SessionLocal


class StaffPermissionsMiddleware(BaseHTTPMiddleware):
    """Mantém planeamento, scouting e jogos em consulta para o staff."""

    _metodos_leitura = {"GET", "HEAD", "OPTIONS"}
    _areas_consulta = ("/planeamento", "/planeamento-clube", "/treino", "/agenda", "/scouting", "/jogos")
    _paginas_de_edicao = re.compile(
        r"/(?:novo|editar|eliminar|apagar|duplicar|importar|publicar|cancelar)(?:/|$)"
    )

    async def dispatch(self, request, call_next):
        caminho = request.url.path
        if caminho.startswith("/static"):
            return await call_next(request)

        db = SessionLocal()
        try:
            utilizador = obter_utilizador_atual(request, db)
            if not utilizador or utilizador.perfil.value != "staff":
                return await call_next(request)

            area_em_consulta = caminho.startswith(self._areas_consulta)
            bloqueado = area_em_consulta and (
                request.method not in self._metodos_leitura
                or bool(self._paginas_de_edicao.search(caminho))
            )
            if not bloqueado:
                return await call_next(request)

            if request.headers.get("accept", "").startswith("application/json") or request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JSONResponse(status_code=403, content={"detail": "Esta conta de staff não pode alterar esta área."})
            return RedirectResponse(url="/dashboard", status_code=303)
        finally:
            db.close()

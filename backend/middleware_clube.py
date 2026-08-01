from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import HTMLResponse, RedirectResponse

from auth import verificar_token
from clube_contexto import definir_clube_atual, repor_clube_atual
from database import SessionLocal
from models.clube import Clube, EstadoClubeEnum
from models.utilizador import PerfilEnum, Utilizador


class ClubeContextoMiddleware(BaseHTTPMiddleware):
    """Determina o clube a partir da sessão autenticada e protege os seus estados."""

    async def dispatch(self, request, call_next):
        token_contexto = definir_clube_atual(None)
        try:
            request.state.clube_atual = None
            token = request.session.get("token")
            payload = verificar_token(token) if token else None
            if payload:
                db = SessionLocal()
                try:
                    utilizador = db.query(Utilizador).filter(Utilizador.username == payload.get("sub")).first()
                    if utilizador and int(payload.get("sv", 0)) != int(utilizador.sessao_versao or 0):
                        request.session.clear()
                        utilizador = None
                    clube_id = None
                    if utilizador:
                        if utilizador.perfil == PerfilEnum.superadministrador:
                            clube_id = request.session.get("clube_suporte_id")
                        else:
                            clube_id = utilizador.clube_id
                    if clube_id:
                        clube = db.query(Clube).execution_options(ignorar_clube=True).filter(Clube.id == clube_id).first()
                        if clube:
                            definir_clube_atual(clube.id)
                            request.state.clube_atual = clube
                            if utilizador.perfil != PerfilEnum.superadministrador:
                                if clube.estado == EstadoClubeEnum.suspenso:
                                    return HTMLResponse("Clube temporariamente suspenso.", status_code=423)
                                if clube.estado == EstadoClubeEnum.arquivado and request.method not in {"GET", "HEAD", "OPTIONS"}:
                                    return HTMLResponse("Clube arquivado: acesso apenas de leitura.", status_code=403)
                    if utilizador and utilizador.deve_alterar_password and request.url.path not in {"/minha-conta", "/minha-conta/alterar-password", "/logout"}:
                        return RedirectResponse("/minha-conta", status_code=303)
                finally:
                    db.close()
            return await call_next(request)
        finally:
            repor_clube_atual(token_contexto)

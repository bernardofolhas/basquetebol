import secrets
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.requests import Request
from starlette.responses import HTMLResponse

CSRF_SESSION_KEY = "_csrf"
CSRF_FORM_FIELD = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"

# Endpoints isentos de validação CSRF (sem sessão estabelecida)
_CSRF_EXEMPT = {"/login-form", "/health", "/ready"}


def gerar_csrf_token(request: Request) -> str:
    """Garante que existe um token CSRF na sessão e devolve-o."""
    if CSRF_SESSION_KEY not in request.session:
        request.session[CSRF_SESSION_KEY] = secrets.token_hex(32)
    return request.session[CSRF_SESSION_KEY]


class CSRFMiddleware:
    """
    Middleware que protege todos os endpoints POST contra CSRF.

    Estratégia:
    - GET: garante que existe um token CSRF na sessão.
    - POST: lê e re-injeta o corpo, extrai o campo csrf_token (ou
      o header X-CSRF-Token para pedidos HTMX/AJAX) e compara com
      o token guardado na sessão.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        path = request.url.path

        if request.method == "GET":
            gerar_csrf_token(request)
            await self.app(scope, receive, send)
            return

        if request.method == "POST" and path not in _CSRF_EXEMPT:
            session_token = request.session.get(CSRF_SESSION_KEY, "")

            # HTMX / AJAX: token no header (não requer leitura do body)
            header_token = request.headers.get(CSRF_HEADER, "")
            if header_token:
                if not (session_token and secrets.compare_digest(session_token, header_token)):
                    await self._recusar(scope, receive, send)
                    return
                await self.app(scope, receive, send)
                return

            # Formulário HTML normal: token no body
            body = await request.body()

            form_token = _extrair_csrf_do_body(body, request.headers.get("content-type", ""))

            if not (session_token and form_token and secrets.compare_digest(session_token, form_token)):
                await self._recusar(scope, receive, send)
                return

            # Re-injeta o body para que o FastAPI o possa ler normalmente
            body_consumed = False

            async def receive_com_body():
                nonlocal body_consumed
                if not body_consumed:
                    body_consumed = True
                    return {"type": "http.request", "body": body, "more_body": False}
                return {"type": "http.disconnect"}

            await self.app(scope, receive_com_body, send)
            return

        await self.app(scope, receive, send)

    @staticmethod
    async def _recusar(scope: Scope, receive: Receive, send: Send) -> None:
        response = HTMLResponse(
            "<h1>Sessão expirada ou pedido inválido</h1>"
            "<p><a href='/login'>Voltar ao login</a></p>",
            status_code=403,
        )
        await response(scope, receive, send)


def _extrair_csrf_do_body(body: bytes, content_type: str) -> str:
    """Extrai o valor do campo csrf_token do body de um formulário."""
    if not body:
        return ""

    if "multipart/form-data" in content_type:
        # Para multipart, procura o campo pelo nome sem parsear tudo
        decoded = body.decode("latin-1")
        marker = f'name="{CSRF_FORM_FIELD}"'
        idx = decoded.find(marker)
        if idx == -1:
            return ""
        # O valor vem após dois \r\n
        start = decoded.find("\r\n\r\n", idx)
        if start == -1:
            return ""
        start += 4
        end = decoded.find("\r\n", start)
        return decoded[start:end].strip() if end != -1 else decoded[start:].strip()

    # application/x-www-form-urlencoded (mais comum)
    from urllib.parse import parse_qs
    try:
        fields = parse_qs(body.decode("utf-8"))
        values = fields.get(CSRF_FORM_FIELD, [""])
        return values[0] if values else ""
    except Exception:
        return ""

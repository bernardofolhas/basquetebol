from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.requests import Request

_FLASH_SESSION_KEY = "_flash"


def set_flash(request: Request, mensagem: str, tipo: str = "success") -> None:
    """Guarda uma mensagem flash na sessão para ser exibida na próxima página."""
    request.session[_FLASH_SESSION_KEY] = {"mensagem": mensagem, "tipo": tipo}


class FlashMiddleware:
    """
    Middleware que lê a mensagem flash da sessão e disponibiliza-a em
    request.state.flash, limpando-a da sessão ao mesmo tempo.

    Deve ser adicionado ANTES do SessionMiddleware para correr depois dele
    (a ordem de add_middleware é LIFO para o processamento do pedido).
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            request = Request(scope, receive)
            flash = request.session.pop(_FLASH_SESSION_KEY, None)
            request.state.flash = flash
        await self.app(scope, receive, send)

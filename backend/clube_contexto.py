from contextvars import ContextVar


_clube_atual_id: ContextVar[int | None] = ContextVar("clube_atual_id", default=None)


def clube_atual_id() -> int | None:
    return _clube_atual_id.get()


def definir_clube_atual(clube_id: int | None):
    return _clube_atual_id.set(clube_id)


def repor_clube_atual(token) -> None:
    _clube_atual_id.reset(token)

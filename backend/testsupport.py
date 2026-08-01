import json
from base64 import b64decode
from urllib.parse import urlsplit

from fastapi.testclient import TestClient as FastAPITestClient
from itsdangerous import BadSignature, TimestampSigner

from config import config
from csrf import CSRF_HEADER, CSRF_SESSION_KEY

CSRF_EXEMPT_PATHS = {"/login-form", "/health", "/ready"}


class TestClient(FastAPITestClient):
    """Cliente de testes com gestão automática de CSRF para formulários POST."""

    def _resolver_path(self, url: str) -> str:
        return urlsplit(url).path or url

    def _ler_sessao(self) -> dict:
        cookie = self.cookies.get(config.session_cookie_name)
        if not cookie or cookie == "null":
            return {}

        signer = TimestampSigner(str(config.session_secret_key))
        try:
            data = signer.unsign(
                cookie.encode("utf-8"),
                max_age=config.session_cookie_max_age_seconds,
            )
        except BadSignature:
            return {}

        try:
            return json.loads(b64decode(data))
        except Exception:
            return {}

    def _obter_token_csrf(self) -> str:
        sessao = self._ler_sessao()
        token = sessao.get(CSRF_SESSION_KEY, "")
        if token:
            return token

        # Um GET gera automaticamente o token CSRF na sessão.
        super().get("/dashboard", follow_redirects=False)
        sessao = self._ler_sessao()
        return sessao.get(CSRF_SESSION_KEY, "")

    def post(self, url, *args, **kwargs):
        path = self._resolver_path(str(url))
        headers = dict(kwargs.pop("headers", {}) or {})

        if path not in CSRF_EXEMPT_PATHS and CSRF_HEADER not in headers:
            token = self._obter_token_csrf()
            if token:
                headers[CSRF_HEADER] = token

        if headers:
            kwargs["headers"] = headers

        return super().post(url, *args, **kwargs)

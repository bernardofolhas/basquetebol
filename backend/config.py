import os
from dataclasses import dataclass

from dotenv import load_dotenv
from logging_config import obter_logger
from paths import BASE_DIR, ENV_FILE

logger = obter_logger(__name__)

# Carrega as variáveis de ambiente a partir do ficheiro .env do projecto.
load_dotenv(dotenv_path=ENV_FILE)


@dataclass(frozen=True)
class Configuracao:
    """
    Centraliza a configuração base da aplicação.

    Mantemos compatibilidade com o `.env` actual e permitimos introduzir
    variáveis mais específicas para produção sem alterar o restante código.
    """

    database_url: str
    secret_key: str
    session_secret_key: str
    algorithm: str
    access_token_expire_minutes: int
    ambiente: str
    session_cookie_name: str
    session_cookie_same_site: str
    session_cookie_https_only: bool
    session_cookie_max_age_seconds: int
    session_cookie_domain: str | None
    app_base_url: str
    smtp_host: str | None
    smtp_port: int
    smtp_username: str | None
    smtp_password: str | None
    smtp_from_email: str | None
    smtp_use_tls: bool
    brevo_api_key: str | None
    fiba_stats_api_url_template: str | None
    fiba_stats_api_key: str | None
    fiba_stats_api_key_header: str


def _obter_variavel_obrigatoria(nome: str) -> str:
    """
    Lê uma variável obrigatória e falha cedo se estiver em falta.
    """
    valor = os.getenv(nome)
    if not valor:
        mensagem = (
            f"A variável de ambiente '{nome}' é obrigatória. "
            f"Confirma o ficheiro {ENV_FILE} ou as variáveis do ambiente actual."
        )
        logger.error(mensagem)
        raise RuntimeError(mensagem)
    return valor


def _normalizar_database_url(database_url: str) -> str:
    """
    Converte caminhos relativos de SQLite em caminhos absolutos.
    """
    if not database_url.startswith("sqlite") or ":///" not in database_url:
        return database_url

    prefixo, separador, caminho = database_url.partition(":///")
    if not separador or not caminho or caminho == ":memory:" or caminho.startswith("/"):
        return database_url

    caminho_absoluto = (BASE_DIR / caminho).resolve()
    return f"{prefixo}:///{caminho_absoluto.as_posix()}"


def _obter_bool_ambiente(nome: str, default: bool) -> bool:
    """Interpreta uma flag booleana de ambiente de forma previsivel."""
    valor = os.getenv(nome)
    if valor is None:
        return default

    valor_normalizado = valor.strip().lower()
    if valor_normalizado in {"1", "true", "yes", "on", "sim"}:
        return True
    if valor_normalizado in {"0", "false", "no", "off", "nao", "não"}:
        return False

    raise RuntimeError(f"A variável '{nome}' deve ser booleana (true/false).")


def _obter_int_ambiente(nome: str, default: int, *, minimo: int = 1) -> int:
    """Lê um inteiro positivo do ambiente com validação básica."""
    valor = os.getenv(nome)
    if valor is None or not valor.strip():
        return default

    try:
        inteiro = int(valor)
    except ValueError as exc:
        raise RuntimeError(f"A variável '{nome}' deve ser um número inteiro.") from exc

    if inteiro < minimo:
        raise RuntimeError(f"A variável '{nome}' deve ser >= {minimo}.")
    return inteiro


def _normalizar_same_site(valor: str | None) -> str:
    """Normaliza o valor de SameSite para os formatos aceites pelo Starlette."""
    valor_normalizado = (valor or "lax").strip().lower()
    if valor_normalizado not in {"lax", "strict", "none"}:
        raise RuntimeError("SESSION_COOKIE_SAME_SITE deve ser 'lax', 'strict' ou 'none'.")
    return valor_normalizado


def _criar_configuracao() -> Configuracao:
    """
    Constrói a configuração global da aplicação.

    Se `SESSION_SECRET_KEY` ainda não existir, reutilizamos `SECRET_KEY`
    apenas fora de produção para manter compatibilidade com o ambiente actual.
    """
    ambiente = os.getenv("APP_ENV", "development").strip().lower()

    if not ENV_FILE.exists():
        logger.warning(
            "Ficheiro .env não encontrado em %s. Serão usadas apenas variáveis de ambiente já definidas.",
            ENV_FILE,
        )

    secret_key = _obter_variavel_obrigatoria("SECRET_KEY")
    database_url = _normalizar_database_url(_obter_variavel_obrigatoria("DATABASE_URL"))
    session_secret_key = os.getenv("SESSION_SECRET_KEY", secret_key)
    access_token_expire_minutes = _obter_int_ambiente("ACCESS_TOKEN_EXPIRE_MINUTES", 480)
    session_cookie_name = os.getenv("SESSION_COOKIE_NAME", "basquetebol_session").strip() or "basquetebol_session"
    session_cookie_same_site = _normalizar_same_site(os.getenv("SESSION_COOKIE_SAME_SITE", "lax"))
    session_cookie_https_only = _obter_bool_ambiente(
        "SESSION_COOKIE_HTTPS_ONLY",
        default=ambiente == "production",
    )
    session_cookie_max_age_seconds = _obter_int_ambiente(
        "SESSION_COOKIE_MAX_AGE_SECONDS",
        access_token_expire_minutes * 60,
        minimo=300,
    )
    session_cookie_domain = os.getenv("SESSION_COOKIE_DOMAIN")
    session_cookie_domain = session_cookie_domain.strip() if session_cookie_domain else None
    app_base_url = os.getenv(
        "APP_BASE_URL",
        "https://basquetebol-production.up.railway.app" if ambiente == "production" else "http://127.0.0.1:8000",
    ).strip().rstrip("/")
    if ambiente == "production" and not app_base_url.startswith("https://"):
        raise RuntimeError("APP_BASE_URL tem de usar HTTPS em produção.")

    if session_secret_key == secret_key:
        if ambiente == "production":
            raise RuntimeError("Em produção, SESSION_SECRET_KEY tem de ser diferente da SECRET_KEY.")
        logger.info("SESSION_SECRET_KEY não definida. Vai ser reutilizada a SECRET_KEY para manter compatibilidade.")

    if session_cookie_same_site == "none" and not session_cookie_https_only:
        raise RuntimeError("SESSION_COOKIE_SAME_SITE=none exige SESSION_COOKIE_HTTPS_ONLY=true.")

    configuracao = Configuracao(
        database_url=database_url,
        secret_key=secret_key,
        session_secret_key=session_secret_key,
        algorithm=os.getenv("ALGORITHM", "HS256"),
        access_token_expire_minutes=access_token_expire_minutes,
        ambiente=ambiente,
        session_cookie_name=session_cookie_name,
        session_cookie_same_site=session_cookie_same_site,
        session_cookie_https_only=session_cookie_https_only,
        session_cookie_max_age_seconds=session_cookie_max_age_seconds,
        session_cookie_domain=session_cookie_domain,
        app_base_url=app_base_url,
        smtp_host=(os.getenv("SMTP_HOST") or "").strip() or None,
        smtp_port=_obter_int_ambiente("SMTP_PORT", 587),
        smtp_username=(os.getenv("SMTP_USERNAME") or "").strip() or None,
        smtp_password=os.getenv("SMTP_PASSWORD") or None,
        smtp_from_email=(os.getenv("SMTP_FROM_EMAIL") or "").strip() or None,
        smtp_use_tls=_obter_bool_ambiente("SMTP_USE_TLS", True),
        brevo_api_key=(os.getenv("BREVO_API_KEY") or "").strip() or None,
        fiba_stats_api_url_template=(os.getenv("FIBA_STATS_API_URL_TEMPLATE") or "").strip() or None,
        fiba_stats_api_key=(os.getenv("FIBA_STATS_API_KEY") or "").strip() or None,
        fiba_stats_api_key_header=(os.getenv("FIBA_STATS_API_KEY_HEADER") or "x-api-key").strip(),
    )

    logger.info("Configuração da aplicação carregada para o ambiente '%s'.", configuracao.ambiente)
    return configuracao


config = _criar_configuracao()

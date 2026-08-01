import logging
import os


_LOGGING_CONFIGURADO = False


def configurar_logging() -> None:
    """
    Configura o logging global da aplicação.
    """
    global _LOGGING_CONFIGURADO

    if _LOGGING_CONFIGURADO:
        return

    ambiente = os.getenv("APP_ENV", "development").lower()
    nivel = logging.DEBUG if ambiente == "development" else logging.INFO

    logging.basicConfig(
        level=nivel,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    _LOGGING_CONFIGURADO = True


def obter_logger(nome: str) -> logging.Logger:
    """
    Devolve um logger já suportado pela configuração central.
    """
    configurar_logging()
    return logging.getLogger(nome)

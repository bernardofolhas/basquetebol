import os
import subprocess
import sys
from pathlib import Path

import uvicorn

RAIZ_PROJETO = Path(__file__).resolve().parent
BACKEND_DIR = RAIZ_PROJETO / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.append(str(BACKEND_DIR))


def _aplicar_migrations_producao() -> None:
    if os.getenv("APP_ENV", "development").lower() != "production":
        return
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(BACKEND_DIR / "alembic.ini"), "upgrade", "head"],
        cwd=BACKEND_DIR,
        check=True,
    )


_aplicar_migrations_producao()

from logging_config import obter_logger
from main import app

logger = obter_logger(__name__)


def _obter_reload() -> bool:
    """
    Activa reload apenas em desenvolvimento local.
    """
    return os.getenv("APP_ENV", "development").lower() == "development"


if __name__ == "__main__":
    logger.info(
        "A iniciar servidor HTTP no ambiente '%s' em %s:%s.",
        os.getenv("APP_ENV", "development").lower(),
        os.getenv("HOST", "0.0.0.0"),
        os.getenv("PORT", "8000"),
    )
    uvicorn.run(
        "main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=_obter_reload(),
    )

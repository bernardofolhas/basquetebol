import os
import sys
from pathlib import Path

import uvicorn

RAIZ_PROJETO = Path(__file__).resolve().parent
BACKEND_DIR = RAIZ_PROJETO / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.append(str(BACKEND_DIR))

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

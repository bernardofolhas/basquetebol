from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = BASE_DIR / "backend"
FRONTEND_DIR = BASE_DIR / "frontend"
TEMPLATES_DIR = FRONTEND_DIR / "templates"
STATIC_DIR = FRONTEND_DIR / "static"
BRANDING_DIR = STATIC_DIR / "uploads" / "branding"
JOGADORES_UPLOAD_DIR = STATIC_DIR / "uploads" / "jogadores"
ENV_FILE = BASE_DIR / ".env"


__all__ = [
    "BASE_DIR",
    "BACKEND_DIR",
    "FRONTEND_DIR",
    "TEMPLATES_DIR",
    "STATIC_DIR",
    "BRANDING_DIR",
    "JOGADORES_UPLOAD_DIR",
    "ENV_FILE",
]

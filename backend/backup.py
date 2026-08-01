"""Cria uma cópia local da base de dados para recuperação operacional.

Uso:
    python backend/backup.py

Em PostgreSQL, o comando requer que `pg_dump` esteja disponível no PATH ou
seja indicado em `PG_DUMP_BIN`. Em SQLite é feita uma cópia consistente do
ficheiro configurado em `DATABASE_URL`.
"""

from datetime import datetime
import os
from pathlib import Path
import sqlite3
import subprocess

from config import config
from database import engine
from paths import BASE_DIR


def _diretorio_backups() -> Path:
    diretorio = Path(os.getenv("BACKUP_DIR", str(BASE_DIR / "backups"))).expanduser()
    diretorio.mkdir(parents=True, exist_ok=True)
    return diretorio


def backup_database() -> Path:
    """Cria e devolve o caminho do backup acabado de gerar."""
    instante = datetime.now().strftime("%Y%m%d_%H%M%S")
    diretorio = _diretorio_backups()
    dialecto = engine.dialect.name

    if dialecto == "sqlite":
        origem = Path(engine.url.database or "")
        if not origem.is_absolute():
            origem = (BASE_DIR / origem).resolve()
        if not origem.exists():
            raise FileNotFoundError(f"A base de dados SQLite não existe: {origem}")
        destino = diretorio / f"basquetebol_{instante}.db"
        # O backup nativo mantém consistência mesmo quando a aplicação está ativa.
        with sqlite3.connect(origem) as ligacao_origem, sqlite3.connect(destino) as ligacao_destino:
            ligacao_origem.backup(ligacao_destino)
        return destino

    if dialecto == "postgresql":
        destino = diretorio / f"basquetebol_{instante}.sql"
        executavel = os.getenv("PG_DUMP_BIN", "pg_dump")
        try:
            subprocess.run(
                [executavel, "--dbname", config.database_url, "--file", str(destino)],
                check=True,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                "pg_dump não foi encontrado. Instala o cliente PostgreSQL ou define PG_DUMP_BIN."
            ) from exc
        except subprocess.CalledProcessError as exc:
            erro = (exc.stderr or exc.stdout or "").strip()
            raise RuntimeError(f"O pg_dump falhou{': ' + erro if erro else '.'}") from exc
        return destino

    raise RuntimeError(f"Motor de base de dados não suportado para backup: {dialecto}")


if __name__ == "__main__":
    print(f"Backup criado em: {backup_database()}")

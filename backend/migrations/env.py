import sys
import os
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool
from alembic import context

# Make the backend directory importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import config as app_config
from database import Base

# Import all models so their tables are registered on Base.metadata
import models.atividade
import models.auditoria
import models.clube
import models.atribuicao_espaco_semanal
import models.equipa
import models.espaco_treino
import models.fisico
import models.jogador
import models.jogo
import models.identidade_clube
import models.planeamento
import models.planeamento_clube
import models.treinador
import models.treino
import models.utilizador

alembic_config = context.config
alembic_config.set_main_option("sqlalchemy.url", app_config.database_url)

if alembic_config.config_file_name is not None:
    fileConfig(alembic_config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = alembic_config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        alembic_config.get_section(alembic_config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

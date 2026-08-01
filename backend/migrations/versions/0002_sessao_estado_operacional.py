"""Adds the operational lifecycle state to training sessions."""

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy import inspect


revision = "0002_sessao_estado"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if context.is_offline_mode():
        op.add_column(
            "sessoes_treino",
            sa.Column("estado", sa.String(), nullable=False, server_default="planeada"),
        )
        return

    bind = op.get_bind()
    if "sessoes_treino" not in inspect(bind).get_table_names():
        return

    colunas = {coluna["name"] for coluna in inspect(bind).get_columns("sessoes_treino")}
    if "estado" not in colunas:
        op.add_column(
            "sessoes_treino",
            sa.Column("estado", sa.String(), nullable=False, server_default="planeada"),
        )


def downgrade() -> None:
    if context.is_offline_mode():
        op.drop_column("sessoes_treino", "estado")
        return

    bind = op.get_bind()
    if "sessoes_treino" not in inspect(bind).get_table_names():
        return

    colunas = {coluna["name"] for coluna in inspect(bind).get_columns("sessoes_treino")}
    if "estado" in colunas:
        op.drop_column("sessoes_treino", "estado")

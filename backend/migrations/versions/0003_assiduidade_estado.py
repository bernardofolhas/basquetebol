"""Adds detailed attendance states while preserving the legacy boolean."""

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy import inspect


revision = "0003_assiduidade_estado"
down_revision = "0002_sessao_estado"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if context.is_offline_mode():
        op.add_column(
            "assiduidade",
            sa.Column("estado", sa.String(), nullable=False, server_default="ausente"),
        )
        op.execute(
            "UPDATE assiduidade SET estado = "
            "CASE WHEN presente THEN 'presente' ELSE 'ausente' END"
        )
        return

    bind = op.get_bind()
    if "assiduidade" not in inspect(bind).get_table_names():
        return
    colunas = {coluna["name"] for coluna in inspect(bind).get_columns("assiduidade")}
    if "estado" not in colunas:
        op.add_column(
            "assiduidade",
            sa.Column("estado", sa.String(), nullable=False, server_default="ausente"),
        )
        op.execute(
            "UPDATE assiduidade SET estado = "
            "CASE WHEN presente THEN 'presente' ELSE 'ausente' END"
        )


def downgrade() -> None:
    if context.is_offline_mode():
        op.drop_column("assiduidade", "estado")
        return

    bind = op.get_bind()
    if "assiduidade" not in inspect(bind).get_table_names():
        return
    colunas = {coluna["name"] for coluna in inspect(bind).get_columns("assiduidade")}
    if "estado" in colunas:
        op.drop_column("assiduidade", "estado")

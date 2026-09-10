"""Adiciona regras de aplicação automática aos questionários.

Revision ID: 0039_regras_questionarios
Revises: 0038_questionarios_personalizados
"""

from alembic import op
import sqlalchemy as sa


revision = "0039_regras_questionarios"
down_revision = "0038_questionarios_personalizados"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    colunas_questionarios = {coluna["name"] for coluna in inspector.get_columns("questionarios_personalizados")}
    if "regra_aplicacao" not in colunas_questionarios:
        op.add_column(
            "questionarios_personalizados",
            sa.Column("regra_aplicacao", sa.String(30), nullable=False, server_default="manual"),
        )
    colunas_aplicacoes = {coluna["name"] for coluna in inspector.get_columns("aplicacoes_questionario")}
    if "automatica" not in colunas_aplicacoes:
        op.add_column(
            "aplicacoes_questionario",
            sa.Column("automatica", sa.Boolean(), nullable=False, server_default=sa.false()),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    colunas_aplicacoes = {coluna["name"] for coluna in inspector.get_columns("aplicacoes_questionario")}
    if "automatica" in colunas_aplicacoes:
        op.drop_column("aplicacoes_questionario", "automatica")
    colunas_questionarios = {coluna["name"] for coluna in inspector.get_columns("questionarios_personalizados")}
    if "regra_aplicacao" in colunas_questionarios:
        op.drop_column("questionarios_personalizados", "regra_aplicacao")

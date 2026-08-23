"""Adiciona treino físico às reservas de espaços.

Revision ID: 0020_treino_fisico
Revises: 0019_plano_semanal_admin
"""

from alembic import op


revision = "0020_treino_fisico"
down_revision = "0019_plano_semanal_admin"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TYPE tipoocupacaoespacoenum ADD VALUE IF NOT EXISTS 'treino_fisico'")


def downgrade():
    # PostgreSQL não permite remover valores de enum sem recriar o tipo.
    pass

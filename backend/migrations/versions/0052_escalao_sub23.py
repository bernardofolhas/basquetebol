"""Adiciona o escalão Sub-23 à enumeração de equipas."""

from alembic import op
import sqlalchemy as sa


revision = "0052_escalao_sub23"
down_revision = "0051_ficha_jogo_equipa_tecnica"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        bind.execute(sa.text("ALTER TYPE escalaoenum ADD VALUE IF NOT EXISTS 'sub23'"))


def downgrade() -> None:
    # PostgreSQL não permite remover valores de enums sem recriar o tipo.
    pass

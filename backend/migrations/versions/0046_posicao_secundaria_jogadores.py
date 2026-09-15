"""Permite registar uma segunda posição por atleta."""

from alembic import op
import sqlalchemy as sa


revision = "0046_posicao_secundaria"
down_revision = "0045_equipas_aleatorias"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    colunas = {coluna["name"] for coluna in inspector.get_columns("jogadores")}
    if "posicao_secundaria" not in colunas:
        op.add_column("jogadores", sa.Column("posicao_secundaria", sa.String(), nullable=True))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    colunas = {coluna["name"] for coluna in inspector.get_columns("jogadores")}
    if "posicao_secundaria" in colunas:
        op.drop_column("jogadores", "posicao_secundaria")

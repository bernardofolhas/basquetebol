"""Add player photograph path."""

import sqlalchemy as sa
from alembic import op


revision = "0009_fotografia_jogador"
down_revision = "0008_tipos_agenda"
branch_labels = None
depends_on = None


def upgrade() -> None:
    colunas = {coluna["name"] for coluna in sa.inspect(op.get_bind()).get_columns("jogadores")}
    if "fotografia" not in colunas:
        op.add_column("jogadores", sa.Column("fotografia", sa.String(), nullable=True))


def downgrade() -> None:
    colunas = {coluna["name"] for coluna in sa.inspect(op.get_bind()).get_columns("jogadores")}
    if "fotografia" in colunas:
        op.drop_column("jogadores", "fotografia")

"""Adiciona a posição em campo aos eventos estatísticos."""

import sqlalchemy as sa
from alembic import op


revision = "0031_posicao_estatistica"
down_revision = "0030_estatisticas"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    colunas = {coluna["name"] for coluna in inspector.get_columns("eventos_estatistica")}
    for nome in ("posicao_x", "posicao_y"):
        if nome not in colunas:
            op.add_column("eventos_estatistica", sa.Column(nome, sa.Float(), nullable=True))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    colunas = {coluna["name"] for coluna in inspector.get_columns("eventos_estatistica")}
    for nome in ("posicao_y", "posicao_x"):
        if nome in colunas:
            op.drop_column("eventos_estatistica", nome)

"""Guarda os minutos oficiais dos atletas importados de FIBA LiveStats."""

from alembic import op
import sqlalchemy as sa


revision = "0061_minutos_oficiais_estatistica"
down_revision = "0060_minutos_rotacoes_plano"
branch_labels = None
depends_on = None


def upgrade() -> None:
    colunas = {coluna["name"] for coluna in sa.inspect(op.get_bind()).get_columns("eventos_estatistica")}
    if "segundos_jogados_oficiais" not in colunas:
        op.add_column("eventos_estatistica", sa.Column("segundos_jogados_oficiais", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("eventos_estatistica", "segundos_jogados_oficiais")

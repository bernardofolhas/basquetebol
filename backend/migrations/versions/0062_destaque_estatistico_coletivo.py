"""Permite guardar um indicador em destaque por adversário."""

from alembic import op
import sqlalchemy as sa


revision = "0062_destaque_estatistico_coletivo"
down_revision = "0061_minutos_oficiais_estatistica"
branch_labels = None
depends_on = None


def upgrade() -> None:
    colunas = {coluna["name"] for coluna in sa.inspect(op.get_bind()).get_columns("scouting_adversarios")}
    with op.batch_alter_table("scouting_adversarios") as batch:
        if "estatistica_destaque" not in colunas:
            batch.add_column(sa.Column("estatistica_destaque", sa.String(12), nullable=True))
        if "estatistica_destaque_tom" not in colunas:
            batch.add_column(sa.Column("estatistica_destaque_tom", sa.String(12), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("scouting_adversarios") as batch:
        batch.drop_column("estatistica_destaque_tom")
        batch.drop_column("estatistica_destaque")

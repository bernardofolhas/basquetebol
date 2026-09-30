"""Adiciona o símbolo da equipa adversária ao dossier de Scouting."""

from alembic import op
import sqlalchemy as sa


revision = "0056_simbolo_adversario"
down_revision = "0055_scouting_individual"
branch_labels = None
depends_on = None


def upgrade() -> None:
    colunas = {coluna["name"] for coluna in sa.inspect(op.get_bind()).get_columns("scouting_adversarios")}
    if "simbolo" not in colunas:
        with op.batch_alter_table("scouting_adversarios") as batch:
            batch.add_column(sa.Column("simbolo", sa.String(length=255), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("scouting_adversarios") as batch:
        batch.drop_column("simbolo")

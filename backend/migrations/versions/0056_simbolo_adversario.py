"""Adiciona o símbolo da equipa adversária ao dossier de Scouting."""

from alembic import op
import sqlalchemy as sa


revision = "0056_simbolo_adversario"
down_revision = "0055_scouting_individual"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("scouting_adversarios") as batch:
        batch.add_column(sa.Column("simbolo", sa.String(length=255), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("scouting_adversarios") as batch:
        batch.drop_column("simbolo")

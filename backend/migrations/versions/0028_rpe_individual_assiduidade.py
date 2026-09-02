"""Adiciona RPE individual aos registos de assiduidade."""

import sqlalchemy as sa
from alembic import op


revision = "0028_rpe_assiduidade"
down_revision = "0027_scouting"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "assiduidade" not in inspector.get_table_names():
        return
    colunas = {coluna["name"] for coluna in inspector.get_columns("assiduidade")}
    if "rpe_individual" not in colunas:
        op.add_column("assiduidade", sa.Column("rpe_individual", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("assiduidade", "rpe_individual")

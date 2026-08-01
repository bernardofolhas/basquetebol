"""Adiciona o logótipo secundário à configuração global do clube."""

import sqlalchemy as sa
from alembic import op

revision = "0013_logos_clube"
down_revision = "0012_isolamento_filhos"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    colunas = {coluna["name"] for coluna in inspector.get_columns("clubes")}
    if "logo_secundario" not in colunas:
        op.add_column("clubes", sa.Column("logo_secundario", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("clubes", "logo_secundario")

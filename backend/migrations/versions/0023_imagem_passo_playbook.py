"""Adiciona imagem alternativa aos passos do playbook."""

import sqlalchemy as sa
from alembic import op

revision = "0023_imagem_passo"
down_revision = "0022_importacao_plano"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "imagem_coach" not in {coluna["name"] for coluna in inspector.get_columns("passos_setplay")}:
        op.add_column("passos_setplay", sa.Column("imagem_coach", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("passos_setplay", "imagem_coach")

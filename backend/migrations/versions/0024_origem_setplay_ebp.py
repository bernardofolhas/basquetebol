"""Distingue jogadas manuais de importacoes EBP."""

import sqlalchemy as sa
from alembic import op

revision = "0024_origem_setplay"
down_revision = "0023_imagem_passo"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    colunas = {coluna["name"] for coluna in inspector.get_columns("setplays")}
    if "origem" not in colunas:
        op.add_column(
            "setplays",
            sa.Column("origem", sa.String(), nullable=False, server_default="manual"),
        )
    op.execute(
        sa.text(
            "UPDATE setplays SET origem = 'ebp' "
            "WHERE descricao LIKE 'Categoria de origem:%'"
        )
    )


def downgrade() -> None:
    op.drop_column("setplays", "origem")

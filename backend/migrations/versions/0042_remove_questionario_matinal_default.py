"""Desativa o Questionário Matinal legado por defeito."""

from alembic import op
import sqlalchemy as sa


revision = "0042_remove_questionario_matinal_default"
down_revision = "0041_questionario_matinal_equipa"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "questionario_matinal_ativo" in {
        coluna["name"] for coluna in inspector.get_columns("equipas")
    }:
        op.alter_column(
            "equipas",
            "questionario_matinal_ativo",
            server_default=sa.false(),
        )
        op.execute(sa.text(
            "UPDATE equipas SET questionario_matinal_ativo = FALSE"
        ))


def downgrade() -> None:
    # O estado anterior não deve reativar silenciosamente um questionário legado.
    pass

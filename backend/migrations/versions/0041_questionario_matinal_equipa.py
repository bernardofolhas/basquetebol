"""Permite retirar o Questionário Matinal por equipa."""

from alembic import op
import sqlalchemy as sa


revision = "0041_questionario_matinal_equipa"
down_revision = "0040_perfil_fisioterapeuta"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "questionario_matinal_ativo" not in {
        coluna["name"] for coluna in inspector.get_columns("equipas")
    }:
        op.add_column(
            "equipas",
            sa.Column(
                "questionario_matinal_ativo",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "questionario_matinal_ativo" in {
        coluna["name"] for coluna in inspector.get_columns("equipas")
    }:
        op.drop_column("equipas", "questionario_matinal_ativo")

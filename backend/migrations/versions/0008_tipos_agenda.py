"""Add the extended activity types to PostgreSQL's existing agenda enum."""

from alembic import context, op


revision = "0008_tipos_agenda"
down_revision = "0007_agenda_niveis_planeamento"
branch_labels = None
depends_on = None


TIPOS = ("folga", "torneio", "viagem", "teste_fisico", "outro")


def upgrade() -> None:
    if context.is_offline_mode():
        for tipo in TIPOS:
            op.execute(
                f"ALTER TYPE tipoeventoplaneamentoclubeenum ADD VALUE IF NOT EXISTS '{tipo}'"
            )
        return

    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for tipo in TIPOS:
        op.execute(
            f"ALTER TYPE tipoeventoplaneamentoclubeenum ADD VALUE IF NOT EXISTS '{tipo}'"
        )


def downgrade() -> None:
    # PostgreSQL não remove valores de enum de forma segura numa migração
    # reversível; manter os valores não afeta os dados existentes.
    pass

"""Adiciona o perfil de fisioterapeuta."""

from alembic import op
import sqlalchemy as sa


revision = "0040_perfil_fisioterapeuta"
down_revision = "0039_regras_questionarios"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        existe = bind.execute(sa.text(
            "SELECT 1 FROM pg_enum "
            "WHERE enumtypid = 'perfilenum'::regtype AND enumlabel = 'fisioterapeuta'"
        )).first()
        if not existe:
            bind.execute(sa.text("ALTER TYPE perfilenum ADD VALUE 'fisioterapeuta'"))


def downgrade() -> None:
    # PostgreSQL não permite remover um valor de enum sem recriar o tipo.
    pass

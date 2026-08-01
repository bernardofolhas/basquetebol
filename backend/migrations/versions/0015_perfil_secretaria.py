"""Adiciona o perfil administrativo de secretaria."""

from alembic import op

revision = "0015_perfil_secretaria"
down_revision = "0014_superadmin_global"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TYPE perfilenum ADD VALUE IF NOT EXISTS 'secretaria'")


def downgrade() -> None:
    # O PostgreSQL não remove valores de enums sem recriar o tipo.
    pass

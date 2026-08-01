"""Permite utilizadores globais sem clube, reservados ao superadministrador."""

from alembic import op

revision = "0014_superadmin_global"
down_revision = "0013_logos_clube"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("utilizadores", "clube_id", nullable=True)


def downgrade() -> None:
    # Só pode ser revertida depois de remover ou associar os superadministradores.
    op.alter_column("utilizadores", "clube_id", nullable=False)

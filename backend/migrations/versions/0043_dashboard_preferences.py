"""Guarda preferências de visualização dos dashboards por utilizador."""

from alembic import op
import sqlalchemy as sa


revision = "0043_dashboard_preferences"
down_revision = "0042_remove_questionario_matinal_default"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "preferencias_dashboard" not in {
        coluna["name"] for coluna in inspector.get_columns("utilizadores")
    }:
        op.add_column(
            "utilizadores",
            sa.Column("preferencias_dashboard", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "preferencias_dashboard" in {
        coluna["name"] for coluna in inspector.get_columns("utilizadores")
    }:
        op.drop_column("utilizadores", "preferencias_dashboard")

"""Link the common agenda with macro, meso and micro planning levels."""

from alembic import context, op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "0007_agenda_niveis_planeamento"
down_revision = "0006_evento_sessao_set_null"
branch_labels = None
depends_on = None


COLUNAS = (
    ("macrociclo_id", "macrociclos", "fk_eventos_agenda_macrociclo"),
    ("mesociclo_id", "mesociclos", "fk_eventos_agenda_mesociclo"),
    ("microciclo_id", "microciclos", "fk_eventos_agenda_microciclo"),
)


def upgrade() -> None:
    if context.is_offline_mode():
        for coluna, tabela, constraint in COLUNAS:
            op.add_column(
                "eventos_planeamento_clube",
                sa.Column(coluna, sa.Integer(), nullable=True),
            )
            op.create_foreign_key(
                constraint,
                "eventos_planeamento_clube",
                tabela,
                [coluna],
                ["id"],
                ondelete="CASCADE",
            )
        return

    inspector = inspect(op.get_bind())
    if "eventos_planeamento_clube" not in inspector.get_table_names():
        return

    existentes = {coluna["name"] for coluna in inspector.get_columns("eventos_planeamento_clube")}
    for coluna, tabela, constraint in COLUNAS:
        if coluna not in existentes:
            op.add_column(
                "eventos_planeamento_clube",
                sa.Column(coluna, sa.Integer(), nullable=True),
            )
        constraints = {item["name"] for item in inspector.get_foreign_keys("eventos_planeamento_clube")}
        if constraint not in constraints:
            op.create_foreign_key(
                constraint,
                "eventos_planeamento_clube",
                tabela,
                [coluna],
                ["id"],
                ondelete="CASCADE",
            )


def downgrade() -> None:
    if context.is_offline_mode():
        for coluna, _tabela, constraint in reversed(COLUNAS):
            op.drop_constraint(constraint, "eventos_planeamento_clube", type_="foreignkey")
            op.drop_column("eventos_planeamento_clube", coluna)
        return

    inspector = inspect(op.get_bind())
    if "eventos_planeamento_clube" not in inspector.get_table_names():
        return
    existentes = {coluna["name"] for coluna in inspector.get_columns("eventos_planeamento_clube")}
    constraints = {item["name"] for item in inspector.get_foreign_keys("eventos_planeamento_clube")}
    for coluna, _tabela, constraint in reversed(COLUNAS):
        if constraint in constraints:
            op.drop_constraint(constraint, "eventos_planeamento_clube", type_="foreignkey")
        if coluna in existentes:
            op.drop_column("eventos_planeamento_clube", coluna)

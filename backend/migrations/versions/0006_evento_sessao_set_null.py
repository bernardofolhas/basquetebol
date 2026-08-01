"""Permite remover eventos sem quebrar sessões sincronizadas."""

from alembic import op
import sqlalchemy as sa


revision = "0006_evento_sessao_set_null"
down_revision = "0005_identidade_clube"
branch_labels = None
depends_on = None


def _nome_constraint_evento(bind):
    inspector = sa.inspect(bind)
    for foreign_key in inspector.get_foreign_keys("sessoes_treino"):
        if foreign_key.get("constrained_columns") == ["evento_planeamento_clube_id"]:
            return foreign_key.get("name")
    return None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    nome_constraint = _nome_constraint_evento(bind)
    if nome_constraint:
        op.drop_constraint(nome_constraint, "sessoes_treino", type_="foreignkey")
    op.create_foreign_key(
        "sessoes_treino_evento_planeamento_clube_id_fkey",
        "sessoes_treino",
        "eventos_planeamento_clube",
        ["evento_planeamento_clube_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    nome_constraint = _nome_constraint_evento(bind)
    if nome_constraint:
        op.drop_constraint(nome_constraint, "sessoes_treino", type_="foreignkey")
    op.create_foreign_key(
        "sessoes_treino_evento_planeamento_clube_id_fkey",
        "sessoes_treino",
        "eventos_planeamento_clube",
        ["evento_planeamento_clube_id"],
        ["id"],
    )

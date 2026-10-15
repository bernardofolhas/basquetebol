"""Associa automaticamente os cadernos de playbook ao adversario."""

from alembic import op
import sqlalchemy as sa


revision = "0063_caderno_scouting_adversario"
down_revision = "0062_destaque_estatistico_coletivo"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    colunas = {coluna["name"] for coluna in inspector.get_columns("cadernos_playbook")}
    if "scouting_adversario_id" not in colunas:
        with op.batch_alter_table("cadernos_playbook") as batch:
            batch.add_column(sa.Column(
                "scouting_adversario_id", sa.Integer(),
                sa.ForeignKey("scouting_adversarios.id", ondelete="SET NULL"), nullable=True,
            ))
    indices = {indice["name"] for indice in sa.inspect(op.get_bind()).get_indexes("cadernos_playbook")}
    restricoes = {
        restricao["name"] for restricao in sa.inspect(op.get_bind()).get_unique_constraints("cadernos_playbook")
    }
    if "ix_cadernos_playbook_scouting_adversario_id" not in indices:
        op.create_index("ix_cadernos_playbook_scouting_adversario_id", "cadernos_playbook", ["scouting_adversario_id"])
    if "uq_caderno_scouting_equipa_adversario" not in indices | restricoes:
        op.create_index("uq_caderno_scouting_equipa_adversario", "cadernos_playbook", ["equipa_id", "scouting_adversario_id"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_caderno_scouting_equipa_adversario", table_name="cadernos_playbook")
    op.drop_index("ix_cadernos_playbook_scouting_adversario_id", table_name="cadernos_playbook")
    with op.batch_alter_table("cadernos_playbook") as batch:
        batch.drop_column("scouting_adversario_id")

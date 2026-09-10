"""Permite várias respostas diárias por atleta.

Revision ID: 0037_respostas_multiplas
Revises: 0036_questionarios_diarios
"""

from alembic import op
import sqlalchemy as sa


revision = "0037_respostas_multiplas"
down_revision = "0036_questionarios_diarios"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    nomes = {
        restricao.get("name")
        for restricao in sa.inspect(bind).get_unique_constraints("respostas_questionario_diario")
    }
    if "uq_questionario_diario_jogador_data" not in nomes:
        return
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("respostas_questionario_diario") as batch:
            batch.drop_constraint("uq_questionario_diario_jogador_data", type_="unique")
    else:
        op.drop_constraint(
            "uq_questionario_diario_jogador_data",
            "respostas_questionario_diario",
            type_="unique",
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("respostas_questionario_diario") as batch:
            batch.create_unique_constraint(
                "uq_questionario_diario_jogador_data", ["jogador_id", "data"]
            )
    else:
        op.create_unique_constraint(
            "uq_questionario_diario_jogador_data",
            "respostas_questionario_diario",
            ["jogador_id", "data"],
        )

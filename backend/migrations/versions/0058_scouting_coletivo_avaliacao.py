"""Adiciona avaliação de zero a cinco ao perfil coletivo."""

from alembic import op
import sqlalchemy as sa


revision = "0058_scouting_coletivo_avaliacao"
down_revision = "0057_scouting_coletivo_modular"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspetor = sa.inspect(op.get_bind())
    colunas = {coluna["name"] for coluna in inspetor.get_columns("scouting_blocos_coletivos")}
    if "avaliacao" not in colunas:
        op.add_column("scouting_blocos_coletivos", sa.Column("avaliacao", sa.Integer(), nullable=True))
    restricoes = {restricao["name"] for restricao in sa.inspect(op.get_bind()).get_check_constraints("scouting_blocos_coletivos")}
    if "ck_scouting_bloco_coletivo_avaliacao" not in restricoes:
        op.create_check_constraint(
            "ck_scouting_bloco_coletivo_avaliacao",
            "scouting_blocos_coletivos",
            "avaliacao IS NULL OR (avaliacao >= 0 AND avaliacao <= 5)",
        )


def downgrade() -> None:
    op.drop_constraint(
        "ck_scouting_bloco_coletivo_avaliacao",
        "scouting_blocos_coletivos",
        type_="check",
    )
    op.drop_column("scouting_blocos_coletivos", "avaliacao")

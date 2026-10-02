"""Liga duas entradas previstas a cada titular do cinco inicial."""

from alembic import op
import sqlalchemy as sa


revision = "0059_substituicoes_previstas"
down_revision = "0058_scouting_coletivo_avaliacao"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "scouting_substituicoes_previstas" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "scouting_substituicoes_previstas",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("clube_id", sa.Integer(), sa.ForeignKey("clubes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("adversario_id", sa.Integer(), sa.ForeignKey("scouting_adversarios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("titular_id", sa.Integer(), sa.ForeignKey("scouting_roster_jogadores.id", ondelete="CASCADE"), nullable=False),
        sa.Column("jogador_id", sa.Integer(), sa.ForeignKey("scouting_roster_jogadores.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ordem", sa.Integer(), nullable=False),
        sa.UniqueConstraint("adversario_id", "titular_id", "ordem", name="uq_scouting_substituicao_titular_ordem"),
        sa.CheckConstraint("ordem IN (1, 2)", name="ck_scouting_substituicao_ordem"),
    )
    op.create_index("ix_scouting_substituicoes_previstas_clube_id", "scouting_substituicoes_previstas", ["clube_id"])
    op.create_index("ix_scouting_substituicoes_previstas_adversario_id", "scouting_substituicoes_previstas", ["adversario_id"])


def downgrade() -> None:
    op.drop_table("scouting_substituicoes_previstas")

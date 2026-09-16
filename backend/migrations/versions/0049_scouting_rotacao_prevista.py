"""Adiciona cinco inicial e principais rotacoes previstas do adversario."""

from alembic import op
import sqlalchemy as sa


revision = "0049_scouting_rotacao_prevista"
down_revision = "0048_scouting_coletivo"
branch_labels = None
depends_on = None

TABELA = "scouting_rotacoes_previstas"


def upgrade() -> None:
    try:
        existentes = set(sa.inspect(op.get_bind()).get_table_names())
    except sa.exc.NoInspectionAvailable:
        existentes = set()
    if TABELA in existentes:
        return
    op.create_table(
        TABELA,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("clube_id", sa.Integer(), sa.ForeignKey("clubes.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("adversario_id", sa.Integer(), sa.ForeignKey("scouting_adversarios.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("jogador_id", sa.Integer(), sa.ForeignKey("scouting_roster_jogadores.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("papel", sa.String(16), nullable=False),
        sa.Column("ordem", sa.Integer(), nullable=False),
        sa.UniqueConstraint("adversario_id", "jogador_id", name="uq_scouting_rotacao_adversario_jogador"),
    )


def downgrade() -> None:
    try:
        existentes = set(sa.inspect(op.get_bind()).get_table_names())
    except sa.exc.NoInspectionAvailable:
        existentes = {TABELA}
    if TABELA in existentes:
        op.drop_table(TABELA)

"""Adiciona o registo offline e idempotente de estatísticas de jogo."""

import sqlalchemy as sa
from alembic import op


revision = "0030_estatisticas"
down_revision = "0029_avaliacoes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "eventos_estatistica" in inspector.get_table_names():
        return
    op.create_table(
        "eventos_estatistica",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("client_uid", sa.String(length=80), nullable=False),
        sa.Column("clube_id", sa.Integer(), sa.ForeignKey("clubes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("equipa_id", sa.Integer(), sa.ForeignKey("equipas.id", ondelete="CASCADE"), nullable=False),
        sa.Column("jogo_id", sa.Integer(), sa.ForeignKey("jogos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("jogador_id", sa.Integer(), sa.ForeignKey("jogadores.id", ondelete="SET NULL"), nullable=True),
        sa.Column("registado_por_id", sa.Integer(), sa.ForeignKey("utilizadores.id", ondelete="SET NULL"), nullable=True),
        sa.Column("lado", sa.String(length=16), nullable=False, server_default="equipa"),
        sa.Column("tipo", sa.String(length=32), nullable=False),
        sa.Column("periodo", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("segundos_restantes", sa.Integer(), nullable=True),
        sa.Column("anulado", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(), nullable=False),
    )
    for coluna in ("client_uid", "clube_id", "equipa_id", "jogo_id", "jogador_id", "tipo"):
        op.create_index(f"ix_eventos_estatistica_{coluna}", "eventos_estatistica", [coluna], unique=coluna == "client_uid")


def downgrade() -> None:
    op.drop_table("eventos_estatistica")

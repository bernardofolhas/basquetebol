"""Estrutura rotações, prioridades e jogadas do plano de jogo."""

from alembic import op
import sqlalchemy as sa


revision = "0053_plano_jogo_estruturado"
down_revision = "0052_escalao_sub23"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "plano_jogo_rotacoes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("clube_id", sa.Integer(), sa.ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("plano_jogo_id", sa.Integer(), sa.ForeignKey("planos_jogo.id", ondelete="CASCADE"), nullable=False),
        sa.Column("grupo", sa.Integer(), nullable=False),
        sa.Column("ordem", sa.Integer(), nullable=False),
        sa.Column("jogador_id", sa.Integer(), sa.ForeignKey("jogadores.id", ondelete="CASCADE"), nullable=False),
        sa.UniqueConstraint("plano_jogo_id", "grupo", "ordem", name="uq_plano_rotacao_posicao"),
    )
    op.create_index("ix_plano_jogo_rotacoes_clube_id", "plano_jogo_rotacoes", ["clube_id"])
    op.create_index("ix_plano_jogo_rotacoes_plano_jogo_id", "plano_jogo_rotacoes", ["plano_jogo_id"])
    op.create_index("ix_plano_jogo_rotacoes_jogador_id", "plano_jogo_rotacoes", ["jogador_id"])

    op.create_table(
        "plano_jogo_biblioteca",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("clube_id", sa.Integer(), sa.ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("equipa_id", sa.Integer(), sa.ForeignKey("equipas.id", ondelete="CASCADE"), nullable=False),
        sa.Column("categoria", sa.String(length=48), nullable=False),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.Column("texto_normalizado", sa.String(length=240), nullable=False),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("equipa_id", "categoria", "texto_normalizado", name="uq_plano_biblioteca_item"),
    )
    op.create_index("ix_plano_jogo_biblioteca_clube_id", "plano_jogo_biblioteca", ["clube_id"])
    op.create_index("ix_plano_jogo_biblioteca_equipa_id", "plano_jogo_biblioteca", ["equipa_id"])
    op.create_index("ix_plano_jogo_biblioteca_categoria", "plano_jogo_biblioteca", ["categoria"])

    op.create_table(
        "plano_jogo_itens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("clube_id", sa.Integer(), sa.ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("plano_jogo_id", sa.Integer(), sa.ForeignKey("planos_jogo.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("plano_jogo_biblioteca.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ordem", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("plano_jogo_id", "item_id", name="uq_plano_jogo_item"),
    )
    op.create_index("ix_plano_jogo_itens_clube_id", "plano_jogo_itens", ["clube_id"])
    op.create_index("ix_plano_jogo_itens_plano_jogo_id", "plano_jogo_itens", ["plano_jogo_id"])
    op.create_index("ix_plano_jogo_itens_item_id", "plano_jogo_itens", ["item_id"])

    op.create_table(
        "plano_jogo_jogadas",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("clube_id", sa.Integer(), sa.ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("plano_jogo_id", sa.Integer(), sa.ForeignKey("planos_jogo.id", ondelete="CASCADE"), nullable=False),
        sa.Column("setplay_id", sa.Integer(), sa.ForeignKey("setplays.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ordem", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("plano_jogo_id", "setplay_id", name="uq_plano_jogo_setplay"),
    )
    op.create_index("ix_plano_jogo_jogadas_clube_id", "plano_jogo_jogadas", ["clube_id"])
    op.create_index("ix_plano_jogo_jogadas_plano_jogo_id", "plano_jogo_jogadas", ["plano_jogo_id"])
    op.create_index("ix_plano_jogo_jogadas_setplay_id", "plano_jogo_jogadas", ["setplay_id"])


def downgrade() -> None:
    op.drop_table("plano_jogo_jogadas")
    op.drop_table("plano_jogo_itens")
    op.drop_table("plano_jogo_biblioteca")
    op.drop_table("plano_jogo_rotacoes")

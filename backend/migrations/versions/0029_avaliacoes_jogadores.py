"""Adiciona parâmetros e avaliações individuais de jogadores."""

import sqlalchemy as sa
from alembic import op


revision = "0029_avaliacoes"
down_revision = "0028_rpe_assiduidade"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tabelas = set(inspector.get_table_names())

    if "parametros_avaliacao" not in tabelas:
        op.create_table(
            "parametros_avaliacao",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("clube_id", sa.Integer(), sa.ForeignKey("clubes.id", ondelete="CASCADE"), nullable=False),
            sa.Column("equipa_id", sa.Integer(), sa.ForeignKey("equipas.id", ondelete="CASCADE"), nullable=False),
            sa.Column("nome", sa.String(length=120), nullable=False),
            sa.Column("categoria", sa.String(length=30), nullable=False),
            sa.Column("descricao", sa.Text(), nullable=True),
            sa.Column("valor_minimo", sa.Float(), nullable=False, server_default="0"),
            sa.Column("valor_maximo", sa.Float(), nullable=False, server_default="5"),
            sa.Column("unidade", sa.String(length=30), nullable=True),
            sa.Column("ordem", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("criado_em", sa.DateTime(), nullable=False),
            sa.Column("atualizado_em", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_parametros_avaliacao_clube_id", "parametros_avaliacao", ["clube_id"])
        op.create_index("ix_parametros_avaliacao_equipa_id", "parametros_avaliacao", ["equipa_id"])
        op.create_index("ix_parametros_avaliacao_categoria", "parametros_avaliacao", ["categoria"])

    inspector = sa.inspect(op.get_bind())
    if "avaliacoes_jogadores" not in inspector.get_table_names():
        op.create_table(
            "avaliacoes_jogadores",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("clube_id", sa.Integer(), sa.ForeignKey("clubes.id", ondelete="CASCADE"), nullable=False),
            sa.Column("equipa_id", sa.Integer(), sa.ForeignKey("equipas.id", ondelete="CASCADE"), nullable=False),
            sa.Column("jogador_id", sa.Integer(), sa.ForeignKey("jogadores.id", ondelete="CASCADE"), nullable=False),
            sa.Column("parametro_id", sa.Integer(), sa.ForeignKey("parametros_avaliacao.id", ondelete="CASCADE"), nullable=False),
            sa.Column("sessao_id", sa.Integer(), sa.ForeignKey("sessoes_treino.id", ondelete="CASCADE"), nullable=True),
            sa.Column("avaliador_id", sa.Integer(), sa.ForeignKey("utilizadores.id", ondelete="SET NULL"), nullable=True),
            sa.Column("data", sa.Date(), nullable=False),
            sa.Column("valor", sa.Float(), nullable=False),
            sa.Column("observacao", sa.Text(), nullable=True),
            sa.Column("criado_em", sa.DateTime(), nullable=False),
            sa.Column("atualizado_em", sa.DateTime(), nullable=False),
        )
        for coluna in ("clube_id", "equipa_id", "jogador_id", "parametro_id", "sessao_id", "avaliador_id", "data"):
            op.create_index(f"ix_avaliacoes_jogadores_{coluna}", "avaliacoes_jogadores", [coluna])


def downgrade() -> None:
    op.drop_table("avaliacoes_jogadores")
    op.drop_table("parametros_avaliacao")

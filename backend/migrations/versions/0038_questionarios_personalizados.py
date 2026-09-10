"""Adiciona questionários personalizados, aplicações e respostas.

Revision ID: 0038_questionarios_personalizados
Revises: 0037_respostas_multiplas
"""

from alembic import op
import sqlalchemy as sa


revision = "0038_questionarios_personalizados"
down_revision = "0037_respostas_multiplas"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("questionarios_personalizados"):
        op.create_table(
            "questionarios_personalizados",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("clube_id", sa.Integer(), sa.ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("equipa_id", sa.Integer(), sa.ForeignKey("equipas.id", ondelete="CASCADE"), nullable=False),
            sa.Column("nome", sa.String(180), nullable=False),
            sa.Column("descricao", sa.Text(), nullable=True),
            sa.Column("origem_modelo", sa.String(80), nullable=True),
            sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("criado_em", sa.DateTime(), nullable=False),
            sa.Column("atualizado_em", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_questionarios_personalizados_clube_id", "questionarios_personalizados", ["clube_id"])
        op.create_index("ix_questionarios_personalizados_equipa_id", "questionarios_personalizados", ["equipa_id"])
    if not inspector.has_table("perguntas_questionario"):
        op.create_table(
            "perguntas_questionario",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("questionario_id", sa.Integer(), sa.ForeignKey("questionarios_personalizados.id", ondelete="CASCADE"), nullable=False),
            sa.Column("texto", sa.String(300), nullable=False),
            sa.Column("ajuda", sa.String(300), nullable=True),
            sa.Column("tipo", sa.String(30), nullable=False),
            sa.Column("obrigatoria", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("ordem", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("minimo", sa.Float(), nullable=True),
            sa.Column("maximo", sa.Float(), nullable=True),
            sa.Column("rotulo_minimo", sa.String(80), nullable=True),
            sa.Column("rotulo_maximo", sa.String(80), nullable=True),
            sa.Column("opcoes_json", sa.Text(), nullable=True),
        )
        op.create_index("ix_perguntas_questionario_questionario_id", "perguntas_questionario", ["questionario_id"])
    if not inspector.has_table("aplicacoes_questionario"):
        op.create_table(
            "aplicacoes_questionario",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("clube_id", sa.Integer(), sa.ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("equipa_id", sa.Integer(), sa.ForeignKey("equipas.id", ondelete="CASCADE"), nullable=False),
            sa.Column("questionario_id", sa.Integer(), sa.ForeignKey("questionarios_personalizados.id", ondelete="CASCADE"), nullable=False),
            sa.Column("sessao_treino_id", sa.Integer(), sa.ForeignKey("sessoes_treino.id", ondelete="SET NULL"), nullable=True),
            sa.Column("data", sa.Date(), nullable=False),
            sa.Column("titulo", sa.String(180), nullable=True),
            sa.Column("permite_multiplas", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("ativa", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("criado_em", sa.DateTime(), nullable=False),
        )
        for coluna in ("clube_id", "equipa_id", "questionario_id", "sessao_treino_id", "data"):
            op.create_index(f"ix_aplicacoes_questionario_{coluna}", "aplicacoes_questionario", [coluna])
    if not inspector.has_table("submissoes_questionario"):
        op.create_table(
            "submissoes_questionario",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("clube_id", sa.Integer(), sa.ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("aplicacao_id", sa.Integer(), sa.ForeignKey("aplicacoes_questionario.id", ondelete="CASCADE"), nullable=False),
            sa.Column("jogador_id", sa.Integer(), sa.ForeignKey("jogadores.id", ondelete="CASCADE"), nullable=False),
            sa.Column("criado_em", sa.DateTime(), nullable=False),
            sa.Column("atualizado_em", sa.DateTime(), nullable=False),
        )
        for coluna in ("clube_id", "aplicacao_id", "jogador_id"):
            op.create_index(f"ix_submissoes_questionario_{coluna}", "submissoes_questionario", [coluna])
    if not inspector.has_table("respostas_perguntas_questionario"):
        op.create_table(
            "respostas_perguntas_questionario",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("submissao_id", sa.Integer(), sa.ForeignKey("submissoes_questionario.id", ondelete="CASCADE"), nullable=False),
            sa.Column("pergunta_id", sa.Integer(), sa.ForeignKey("perguntas_questionario.id", ondelete="CASCADE"), nullable=False),
            sa.Column("valor", sa.Text(), nullable=True),
            sa.UniqueConstraint("submissao_id", "pergunta_id", name="uq_resposta_submissao_pergunta"),
        )
        op.create_index("ix_respostas_perguntas_questionario_submissao_id", "respostas_perguntas_questionario", ["submissao_id"])
        op.create_index("ix_respostas_perguntas_questionario_pergunta_id", "respostas_perguntas_questionario", ["pergunta_id"])


def downgrade() -> None:
    for tabela in (
        "respostas_perguntas_questionario",
        "submissoes_questionario",
        "aplicacoes_questionario",
        "perguntas_questionario",
        "questionarios_personalizados",
    ):
        if sa.inspect(op.get_bind()).has_table(tabela):
            op.drop_table(tabela)

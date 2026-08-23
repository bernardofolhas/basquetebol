"""Adiciona conteúdos planeados às sessões de treino.

Revision ID: 0021_conteudos_sessao
Revises: 0020_treino_fisico
"""

from alembic import op
import sqlalchemy as sa


revision = "0021_conteudos_sessao"
down_revision = "0020_treino_fisico"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    colunas_sessao = {coluna["name"] for coluna in inspector.get_columns("sessoes_treino")}
    if "min_psicologicos" not in colunas_sessao:
        op.add_column(
            "sessoes_treino",
            sa.Column("min_psicologicos", sa.Integer(), nullable=False, server_default="0"),
        )
    if not inspector.has_table("conteudos_sessao_treino"):
        op.create_table(
            "conteudos_sessao_treino",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("sessao_id", sa.Integer(), sa.ForeignKey("sessoes_treino.id", ondelete="CASCADE"), nullable=False),
            sa.Column("categoria", sa.String(length=64), nullable=False),
            sa.Column("descricao", sa.Text(), nullable=False),
            sa.Column("minutos", sa.Integer(), nullable=False),
            sa.Column("ordem", sa.Integer(), nullable=False, server_default="0"),
        )
        op.create_index("ix_conteudos_sessao_treino_sessao_id", "conteudos_sessao_treino", ["sessao_id"])


def downgrade():
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("conteudos_sessao_treino"):
        op.drop_index("ix_conteudos_sessao_treino_sessao_id", table_name="conteudos_sessao_treino")
        op.drop_table("conteudos_sessao_treino")
    colunas_sessao = {coluna["name"] for coluna in inspector.get_columns("sessoes_treino")}
    if "min_psicologicos" in colunas_sessao:
        op.drop_column("sessoes_treino", "min_psicologicos")

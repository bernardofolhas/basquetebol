"""Guarda ficheiros e rascunhos reconhecidos de planos de treino.

Revision ID: 0022_importacao_plano
Revises: 0021_conteudos_sessao
"""

from alembic import op
import sqlalchemy as sa


revision = "0022_importacao_plano"
down_revision = "0021_conteudos_sessao"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("importacoes_plano_treino"):
        return
    op.create_table(
        "importacoes_plano_treino",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("clube_id", sa.Integer(), sa.ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("plano_id", sa.Integer(), sa.ForeignKey("planos_treino.id", ondelete="CASCADE"), nullable=False),
        sa.Column("utilizador_id", sa.Integer(), sa.ForeignKey("utilizadores.id", ondelete="SET NULL"), nullable=True),
        sa.Column("nome_original", sa.String(length=255), nullable=False),
        sa.Column("tipo_mime", sa.String(length=120), nullable=False),
        sa.Column("tamanho_bytes", sa.Integer(), nullable=False),
        sa.Column("ficheiro", sa.LargeBinary(), nullable=False),
        sa.Column("texto_extraido", sa.Text(), nullable=True),
        sa.Column("dados_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("estado", sa.String(length=30), nullable=False, server_default="em_revisao"),
        sa.Column("confianca", sa.Float(), nullable=True),
        sa.Column("aviso", sa.Text(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_importacoes_plano_treino_clube_id", "importacoes_plano_treino", ["clube_id"])
    op.create_index("ix_importacoes_plano_treino_plano_id", "importacoes_plano_treino", ["plano_id"])
    op.create_index("ix_importacoes_plano_treino_utilizador_id", "importacoes_plano_treino", ["utilizador_id"])


def downgrade():
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("importacoes_plano_treino"):
        op.drop_table("importacoes_plano_treino")

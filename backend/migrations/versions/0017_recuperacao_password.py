"""Adiciona recuperação segura de palavra-passe.

Revision ID: 0017_recuperacao_password
Revises: 0016_planeamento_anual_equipa
"""

from alembic import op
import sqlalchemy as sa


revision = "0017_recuperacao_password"
down_revision = "0016_planeamento_anual_equipa"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("utilizadores", sa.Column("sessao_versao", sa.Integer(), server_default="0", nullable=False))
    op.create_table(
        "tokens_recuperacao_password",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("clube_id", sa.Integer(), nullable=True),
        sa.Column("utilizador_id", sa.Integer(), nullable=False),
        sa.Column("criado_por_id", sa.Integer(), nullable=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("tipo", sa.String(), nullable=False),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.Column("expira_em", sa.DateTime(), nullable=False),
        sa.Column("utilizado_em", sa.DateTime(), nullable=True),
        sa.Column("pedido_ip", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["clube_id"], ["clubes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["utilizador_id"], ["utilizadores.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["criado_por_id"], ["utilizadores.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_tokens_recuperacao_password_id", "tokens_recuperacao_password", ["id"])
    op.create_index("ix_tokens_recuperacao_password_clube_id", "tokens_recuperacao_password", ["clube_id"])
    op.create_index("ix_tokens_recuperacao_password_utilizador_id", "tokens_recuperacao_password", ["utilizador_id"])
    op.create_index("ix_tokens_recuperacao_password_expira_em", "tokens_recuperacao_password", ["expira_em"])


def downgrade():
    op.drop_table("tokens_recuperacao_password")
    op.drop_column("utilizadores", "sessao_versao")

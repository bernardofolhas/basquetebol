"""Agenda testes físicos nos planos de treino."""

from alembic import op
import sqlalchemy as sa


revision = "0054_testes_fisicos_plano"
down_revision = "0053_plano_jogo_estruturado"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "testes_fisicos_plano",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("clube_id", sa.Integer(), sa.ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("plano_id", sa.Integer(), sa.ForeignKey("planos_treino.id", ondelete="CASCADE"), nullable=False),
        sa.Column("definicao_id", sa.Integer(), sa.ForeignKey("definicoes_testes_fisicos.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("hora", sa.String(), nullable=True),
        sa.Column("minutos", sa.Integer(), nullable=False),
        sa.Column("observacoes", sa.Text(), nullable=True),
    )
    op.create_index("ix_testes_fisicos_plano_clube_id", "testes_fisicos_plano", ["clube_id"])
    op.create_index("ix_testes_fisicos_plano_plano_id", "testes_fisicos_plano", ["plano_id"])
    op.create_index("ix_testes_fisicos_plano_definicao_id", "testes_fisicos_plano", ["definicao_id"])


def downgrade() -> None:
    op.drop_table("testes_fisicos_plano")

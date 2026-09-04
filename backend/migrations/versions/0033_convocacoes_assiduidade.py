"""Adiciona convocatórias pontuais de atletas à folha de assiduidade."""

import sqlalchemy as sa
from alembic import op


revision = "0033_convocacoes_assiduidade"
down_revision = "0032_importacao_fiba"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "convocacoes_assiduidade" in inspector.get_table_names():
        return

    op.create_table(
        "convocacoes_assiduidade",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("clube_id", sa.Integer(), sa.ForeignKey("clubes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sessao_id", sa.Integer(), sa.ForeignKey("sessoes_treino.id", ondelete="CASCADE"), nullable=False),
        sa.Column("jogador_id", sa.Integer(), sa.ForeignKey("jogadores.id", ondelete="CASCADE"), nullable=False),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "sessao_id",
            "jogador_id",
            name="uq_convocacao_assiduidade_sessao_jogador",
        ),
    )
    for nome in ("clube_id", "sessao_id", "jogador_id"):
        op.create_index(f"ix_convocacoes_assiduidade_{nome}", "convocacoes_assiduidade", [nome])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "convocacoes_assiduidade" in inspector.get_table_names():
        op.drop_table("convocacoes_assiduidade")

"""Adiciona predefinicoes pessoais e de equipa para relatorios PDF."""

from alembic import op
import sqlalchemy as sa


revision = "0050_predefinicoes_relatorios"
down_revision = "0049_scouting_rotacao_prevista"
branch_labels = None
depends_on = None

TABELA = "predefinicoes_relatorios"


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
        sa.Column("utilizador_id", sa.Integer(), sa.ForeignKey("utilizadores.id", ondelete="CASCADE"), nullable=True, index=True),
        sa.Column("equipa_id", sa.Integer(), sa.ForeignKey("equipas.id", ondelete="CASCADE"), nullable=True, index=True),
        sa.Column("tipo", sa.String(32), nullable=False, index=True),
        sa.Column("ambito", sa.String(16), nullable=False),
        sa.Column("nome", sa.String(120), nullable=False),
        sa.Column("formato", sa.String(24), nullable=False),
        sa.Column("orientacao", sa.String(16), nullable=False),
        sa.Column("secoes", sa.Text(), nullable=False),
        sa.Column("protegido", sa.Boolean(), nullable=False),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("clube_id", "tipo", "ambito", "utilizador_id", "equipa_id", "nome", name="uq_predefinicao_relatorio_contexto"),
    )


def downgrade() -> None:
    try:
        existentes = set(sa.inspect(op.get_bind()).get_table_names())
    except sa.exc.NoInspectionAvailable:
        existentes = {TABELA}
    if TABELA in existentes:
        op.drop_table(TABELA)

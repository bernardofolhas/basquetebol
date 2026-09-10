"""Adiciona acessos de atleta e questionários diários.

Revision ID: 0036_questionarios_diarios
Revises: 0035_cadernos_playbook
"""

from alembic import op
import sqlalchemy as sa


revision = "0036_questionarios_diarios"
down_revision = "0035_cadernos_playbook"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE perfilenum ADD VALUE IF NOT EXISTS 'atleta'")

    colunas = {coluna["name"] for coluna in inspector.get_columns("utilizadores")}
    if "jogador_id" not in colunas:
        op.add_column("utilizadores", sa.Column("jogador_id", sa.Integer(), nullable=True))
        op.create_foreign_key(
            "fk_utilizadores_jogador_id", "utilizadores", "jogadores",
            ["jogador_id"], ["id"], ondelete="CASCADE",
        )
        op.create_index("ix_utilizadores_jogador_id", "utilizadores", ["jogador_id"], unique=True)

    inspector = sa.inspect(bind)
    if not inspector.has_table("respostas_questionario_diario"):
        op.create_table(
            "respostas_questionario_diario",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("clube_id", sa.Integer(), sa.ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("jogador_id", sa.Integer(), sa.ForeignKey("jogadores.id", ondelete="CASCADE"), nullable=False),
            sa.Column("data", sa.Date(), nullable=False),
            sa.Column("tipo_sessao", sa.String(), nullable=False),
            sa.Column("horas_sono", sa.Float(), nullable=True),
            sa.Column("qualidade_sono", sa.Integer(), nullable=False),
            sa.Column("pse_esforco", sa.Integer(), nullable=False),
            sa.Column("dor_membros_inferiores", sa.Integer(), nullable=False),
            sa.Column("dor_membros_superiores", sa.Integer(), nullable=False),
            sa.Column("tem_queixa", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("descricao_queixa", sa.Text(), nullable=True),
            sa.Column("observacoes", sa.Text(), nullable=True),
            sa.Column("criado_em", sa.DateTime(), nullable=False),
            sa.Column("atualizado_em", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("jogador_id", "data", name="uq_questionario_diario_jogador_data"),
        )
        op.create_index("ix_questionario_diario_clube_id", "respostas_questionario_diario", ["clube_id"])
        op.create_index("ix_questionario_diario_jogador_id", "respostas_questionario_diario", ["jogador_id"])
        op.create_index("ix_questionario_diario_data", "respostas_questionario_diario", ["data"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("respostas_questionario_diario"):
        op.drop_table("respostas_questionario_diario")
    colunas = {coluna["name"] for coluna in sa.inspect(bind).get_columns("utilizadores")}
    if "jogador_id" in colunas:
        op.drop_column("utilizadores", "jogador_id")

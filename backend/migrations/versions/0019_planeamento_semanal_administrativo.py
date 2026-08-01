"""Separa reservas logísticas semanais das sessões técnicas.

Revision ID: 0019_plano_semanal_admin
Revises: 0018_campos_desenho
"""

from alembic import op
import sqlalchemy as sa


revision = "0019_plano_semanal_admin"
down_revision = "0018_campos_desenho"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("atribuicoes_espaco_semanais", sa.Column("treinador_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_atribuicao_semanal_treinador",
        "atribuicoes_espaco_semanais",
        "treinadores",
        ["treinador_id"],
        ["id"],
    )
    op.create_table(
        "disponibilidades_espaco_treino",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("clube_id", sa.Integer(), sa.ForeignKey("clubes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("espaco_id", sa.Integer(), sa.ForeignKey("espacos_treino.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dia_semana", sa.Integer(), nullable=False),
        sa.Column("hora_inicio", sa.String(), nullable=False),
        sa.Column("hora_fim", sa.String(), nullable=False),
        sa.Column("duracao_slot_minutos", sa.Integer(), nullable=False, server_default="90"),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_disponibilidades_espaco_clube", "disponibilidades_espaco_treino", ["clube_id"])
    op.create_index("ix_disponibilidades_espaco", "disponibilidades_espaco_treino", ["espaco_id"])
    op.create_table(
        "indisponibilidades_espaco_treino",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("clube_id", sa.Integer(), sa.ForeignKey("clubes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("espaco_id", sa.Integer(), sa.ForeignKey("espacos_treino.id", ondelete="CASCADE"), nullable=False),
        sa.Column("data_inicio", sa.Date(), nullable=False),
        sa.Column("data_fim", sa.Date(), nullable=False),
        sa.Column("hora_inicio", sa.String(), nullable=True),
        sa.Column("hora_fim", sa.String(), nullable=True),
        sa.Column("motivo", sa.String(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_indisponibilidades_espaco_clube", "indisponibilidades_espaco_treino", ["clube_id"])
    op.create_index("ix_indisponibilidades_espaco", "indisponibilidades_espaco_treino", ["espaco_id"])
    op.create_table(
        "indisponibilidades_treinador",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("clube_id", sa.Integer(), sa.ForeignKey("clubes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("treinador_id", sa.Integer(), sa.ForeignKey("treinadores.id", ondelete="CASCADE"), nullable=False),
        sa.Column("data", sa.Date(), nullable=False),
        sa.Column("hora_inicio", sa.String(), nullable=False),
        sa.Column("hora_fim", sa.String(), nullable=False),
        sa.Column("motivo", sa.String(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_indisponibilidades_treinador_clube", "indisponibilidades_treinador", ["clube_id"])
    op.create_index("ix_indisponibilidades_treinador_id", "indisponibilidades_treinador", ["treinador_id"])
    op.create_index("ix_indisponibilidades_treinador_data", "indisponibilidades_treinador", ["data"])


def downgrade():
    op.drop_table("indisponibilidades_treinador")
    op.drop_table("indisponibilidades_espaco_treino")
    op.drop_table("disponibilidades_espaco_treino")
    op.drop_constraint("fk_atribuicao_semanal_treinador", "atribuicoes_espaco_semanais", type_="foreignkey")
    op.drop_column("atribuicoes_espaco_semanais", "treinador_id")

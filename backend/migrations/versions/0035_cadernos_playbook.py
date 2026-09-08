"""Adiciona cadernos, secções e agrupamento de jogadas ao playbook.

Revision ID: 0035_cadernos_playbook
Revises: 0034_campos_ilimitados
"""

from alembic import op
import sqlalchemy as sa


revision = "0035_cadernos_playbook"
down_revision = "0034_campos_ilimitados"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("cadernos_playbook"):
        op.create_table(
            "cadernos_playbook",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("clube_id", sa.Integer(), sa.ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("equipa_id", sa.Integer(), sa.ForeignKey("equipas.id", ondelete="CASCADE"), nullable=False),
            sa.Column("nome", sa.String(), nullable=False),
            sa.Column("descricao", sa.Text(), nullable=True),
            sa.Column("ordem", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("criado_em", sa.DateTime(), nullable=False),
            sa.Column("atualizado_em", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_cadernos_playbook_clube_id", "cadernos_playbook", ["clube_id"])
        op.create_index("ix_cadernos_playbook_equipa_id", "cadernos_playbook", ["equipa_id"])

    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("secoes_caderno_playbook"):
        op.create_table(
            "secoes_caderno_playbook",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("clube_id", sa.Integer(), sa.ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("caderno_id", sa.Integer(), sa.ForeignKey("cadernos_playbook.id", ondelete="CASCADE"), nullable=False),
            sa.Column("nome", sa.String(), nullable=False),
            sa.Column("ordem", sa.Integer(), nullable=False, server_default="0"),
        )
        op.create_index("ix_secoes_caderno_playbook_clube_id", "secoes_caderno_playbook", ["clube_id"])
        op.create_index("ix_secoes_caderno_playbook_caderno_id", "secoes_caderno_playbook", ["caderno_id"])

    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("jogadas_caderno_playbook"):
        op.create_table(
            "jogadas_caderno_playbook",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("clube_id", sa.Integer(), sa.ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("caderno_id", sa.Integer(), sa.ForeignKey("cadernos_playbook.id", ondelete="CASCADE"), nullable=False),
            sa.Column("secao_id", sa.Integer(), sa.ForeignKey("secoes_caderno_playbook.id", ondelete="SET NULL"), nullable=True),
            sa.Column("setplay_id", sa.Integer(), sa.ForeignKey("setplays.id", ondelete="CASCADE"), nullable=False),
            sa.Column("ordem", sa.Integer(), nullable=False, server_default="0"),
            sa.UniqueConstraint("caderno_id", "setplay_id", name="uq_jogada_caderno_setplay"),
        )
        op.create_index("ix_jogadas_caderno_playbook_clube_id", "jogadas_caderno_playbook", ["clube_id"])
        op.create_index("ix_jogadas_caderno_playbook_caderno_id", "jogadas_caderno_playbook", ["caderno_id"])
        op.create_index("ix_jogadas_caderno_playbook_secao_id", "jogadas_caderno_playbook", ["secao_id"])
        op.create_index("ix_jogadas_caderno_playbook_setplay_id", "jogadas_caderno_playbook", ["setplay_id"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("jogadas_caderno_playbook"):
        op.drop_table("jogadas_caderno_playbook")
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("secoes_caderno_playbook"):
        op.drop_table("secoes_caderno_playbook")
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("cadernos_playbook"):
        op.drop_table("cadernos_playbook")

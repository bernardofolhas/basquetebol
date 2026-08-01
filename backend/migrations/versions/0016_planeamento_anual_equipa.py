"""Adiciona planeamento anual próprio da equipa.

Revision ID: 0016_planeamento_anual_equipa
Revises: 0015_perfil_secretaria
"""

from alembic import op
import sqlalchemy as sa


revision = "0016_planeamento_anual_equipa"
down_revision = "0015_perfil_secretaria"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "planeamentos_anuais_equipa",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("clube_id", sa.Integer(), nullable=False),
        sa.Column("equipa_id", sa.Integer(), nullable=False),
        sa.Column("planeamento_clube_anual_id", sa.Integer(), nullable=True),
        sa.Column("epoca", sa.String(), nullable=False),
        sa.Column("titulo", sa.String(), nullable=False),
        sa.Column("data_inicio", sa.Date(), nullable=False),
        sa.Column("data_fim", sa.Date(), nullable=False),
        sa.Column("objetivos_gerais", sa.Text(), nullable=True),
        sa.Column("obj_tecnica_individual_ofensiva", sa.Text(), nullable=True),
        sa.Column("obj_tecnica_individual_defensiva", sa.Text(), nullable=True),
        sa.Column("obj_tatica_individual_ofensiva", sa.Text(), nullable=True),
        sa.Column("obj_tatica_individual_defensiva", sa.Text(), nullable=True),
        sa.Column("obj_tatica_coletiva_ofensiva", sa.Text(), nullable=True),
        sa.Column("obj_tatica_coletiva_defensiva", sa.Text(), nullable=True),
        sa.Column("obj_fisicos", sa.Text(), nullable=True),
        sa.Column("obj_psicologicos", sa.Text(), nullable=True),
        sa.Column("reflexao", sa.Text(), nullable=True),
        sa.Column("estado", sa.String(), server_default="rascunho", nullable=False),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["clube_id"], ["clubes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["equipa_id"], ["equipas.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["planeamento_clube_anual_id"],
            ["planeamentos_clube_anuais.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_planeamentos_anuais_equipa_id", "planeamentos_anuais_equipa", ["id"])
    op.create_index("ix_planeamentos_anuais_equipa_clube_id", "planeamentos_anuais_equipa", ["clube_id"])
    op.create_index("ix_planeamentos_anuais_equipa_equipa_id", "planeamentos_anuais_equipa", ["equipa_id"])
    op.create_index(
        "ix_planeamentos_anuais_equipa_planeamento_clube_anual_id",
        "planeamentos_anuais_equipa",
        ["planeamento_clube_anual_id"],
    )
    op.add_column("macrociclos", sa.Column("planeamento_anual_equipa_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_macrociclos_planeamento_anual_equipa",
        "macrociclos",
        "planeamentos_anuais_equipa",
        ["planeamento_anual_equipa_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_macrociclos_planeamento_anual_equipa_id",
        "macrociclos",
        ["planeamento_anual_equipa_id"],
    )


def downgrade():
    op.drop_index("ix_macrociclos_planeamento_anual_equipa_id", table_name="macrociclos")
    op.drop_constraint("fk_macrociclos_planeamento_anual_equipa", "macrociclos", type_="foreignkey")
    op.drop_column("macrociclos", "planeamento_anual_equipa_id")
    op.drop_table("planeamentos_anuais_equipa")

"""Permite gerir campos táticos individualmente.

Revision ID: 0018_campos_desenho
Revises: 0017_recuperacao_password
"""

from alembic import op
import sqlalchemy as sa


revision = "0018_campos_desenho"
down_revision = "0017_recuperacao_password"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "exercicios_plano",
        sa.Column("campos_ativos", sa.String(), server_default="1,2", nullable=False),
    )
    op.add_column(
        "biblioteca_exercicios",
        sa.Column("desenho_campo_completo", sa.Text(), nullable=True),
    )
    op.execute(
        """
        UPDATE exercicios_plano
        SET campos_ativos = CASE
            WHEN desenho_3 IS NOT NULL AND desenho_4 IS NOT NULL THEN '1,2,3,4'
            WHEN desenho_3 IS NOT NULL THEN '1,2,3'
            WHEN desenho_4 IS NOT NULL THEN '1,2,4'
            ELSE '1,2'
        END
        """
    )


def downgrade():
    op.drop_column("biblioteca_exercicios", "desenho_campo_completo")
    op.drop_column("exercicios_plano", "campos_ativos")

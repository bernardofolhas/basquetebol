"""Permite adicionar um número variável de campos táticos aos exercícios.

Revision ID: 0034_campos_ilimitados
Revises: 0033_convocacoes_assiduidade
"""

from alembic import op
import sqlalchemy as sa


revision = "0034_campos_ilimitados"
down_revision = "0033_convocacoes_assiduidade"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    colunas = {coluna["name"] for coluna in inspector.get_columns("exercicios_plano")}
    if "desenhos_campos" not in colunas:
        op.add_column(
            "exercicios_plano",
            sa.Column("desenhos_campos", sa.Text(), server_default="{}", nullable=False),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    colunas = {coluna["name"] for coluna in inspector.get_columns("exercicios_plano")}
    if "desenhos_campos" in colunas:
        op.drop_column("exercicios_plano", "desenhos_campos")

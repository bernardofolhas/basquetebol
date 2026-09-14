"""Guarda atletas previstos e equipas aleatórias no plano de treino."""

from alembic import op
import sqlalchemy as sa


revision = "0045_equipas_aleatorias"
down_revision = "0044_catalogo_testes_fisicos"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    colunas = {coluna["name"] for coluna in inspector.get_columns("planos_treino")}
    if "atletas_previstos" not in colunas:
        op.add_column("planos_treino", sa.Column("atletas_previstos", sa.Text(), nullable=True))
    if "equipas_aleatorias" not in colunas:
        op.add_column("planos_treino", sa.Column("equipas_aleatorias", sa.Text(), nullable=True))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    colunas = {coluna["name"] for coluna in inspector.get_columns("planos_treino")}
    if "equipas_aleatorias" in colunas:
        op.drop_column("planos_treino", "equipas_aleatorias")
    if "atletas_previstos" in colunas:
        op.drop_column("planos_treino", "atletas_previstos")

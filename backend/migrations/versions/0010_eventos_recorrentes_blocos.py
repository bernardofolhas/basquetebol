"""Add recurring events, soft deletion and dynamic training blocks."""

import sqlalchemy as sa
from alembic import op

revision = "0010_eventos_blocos"
down_revision = "0009_fotografia_jogador"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    colunas = {item["name"] for item in inspector.get_columns("eventos_planeamento_clube")}
    for nome, coluna in {
        "data_fim": sa.Column("data_fim", sa.Date(), nullable=True),
        "serie_id": sa.Column("serie_id", sa.String(), nullable=True),
        "recorrencia_frequencia": sa.Column("recorrencia_frequencia", sa.String(), nullable=True),
        "recorrencia_intervalo": sa.Column("recorrencia_intervalo", sa.Integer(), nullable=True),
        "ativo": sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
        "alterado_por": sa.Column("alterado_por", sa.String(), nullable=True),
        "desativado_em": sa.Column("desativado_em", sa.DateTime(), nullable=True),
    }.items():
        if nome not in colunas:
            op.add_column("eventos_planeamento_clube", coluna)
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("blocos_treino"):
        op.create_table(
            "blocos_treino",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("plano_id", sa.Integer(), sa.ForeignKey("planos_treino.id", ondelete="CASCADE"), nullable=False),
            sa.Column("nome", sa.String(), nullable=False),
            sa.Column("tipo", sa.String(), nullable=True),
            sa.Column("ordem", sa.Integer(), nullable=False, server_default="1"),
        )
    colunas_exercicios = {item["name"] for item in sa.inspect(op.get_bind()).get_columns("exercicios_plano")}
    if "bloco_id" not in colunas_exercicios:
        op.add_column("exercicios_plano", sa.Column("bloco_id", sa.Integer(), nullable=True))
        op.create_foreign_key("fk_exercicio_bloco", "exercicios_plano", "blocos_treino", ["bloco_id"], ["id"], ondelete="SET NULL")
    indices = {item["name"] for item in sa.inspect(op.get_bind()).get_indexes("eventos_planeamento_clube")}
    if "ix_eventos_serie_id" not in indices:
        op.create_index("ix_eventos_serie_id", "eventos_planeamento_clube", ["serie_id"])
    jogadores = {item["name"] for item in sa.inspect(op.get_bind()).get_columns("jogadores")}
    if "ativo" not in jogadores:
        op.add_column("jogadores", sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    op.drop_column("jogadores", "ativo")
    op.drop_index("ix_eventos_serie_id", table_name="eventos_planeamento_clube")
    op.drop_constraint("fk_exercicio_bloco", "exercicios_plano", type_="foreignkey")
    op.drop_column("exercicios_plano", "bloco_id")
    op.drop_table("blocos_treino")
    for nome in ["desativado_em", "alterado_por", "ativo", "recorrencia_intervalo", "recorrencia_frequencia", "serie_id", "data_fim"]:
        op.drop_column("eventos_planeamento_clube", nome)

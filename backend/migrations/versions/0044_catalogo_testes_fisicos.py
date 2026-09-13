"""Cria catálogo reutilizável e resultados unilaterais dos testes físicos."""

from alembic import op
import sqlalchemy as sa


revision = "0044_catalogo_testes_fisicos"
down_revision = "0043_dashboard_preferences"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "definicoes_testes_fisicos" not in inspector.get_table_names():
        op.create_table(
            "definicoes_testes_fisicos",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("clube_id", sa.Integer(), sa.ForeignKey("clubes.id", ondelete="CASCADE"), nullable=False),
            sa.Column("nome", sa.String(), nullable=False),
            sa.Column("lateralidade", sa.String(), nullable=False, server_default="bilateral"),
            sa.Column("unidade_total", sa.String(), nullable=True),
            sa.Column("unidade_esquerda", sa.String(), nullable=True),
            sa.Column("unidade_direita", sa.String(), nullable=True),
            sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
        )
        op.create_index("ix_definicoes_testes_fisicos_clube_id", "definicoes_testes_fisicos", ["clube_id"])

    colunas = {coluna["name"] for coluna in sa.inspect(op.get_bind()).get_columns("testes_fisicos")}
    novas = {
        "resultado_esquerdo": sa.Column("resultado_esquerdo", sa.Float(), nullable=True),
        "resultado_direito": sa.Column("resultado_direito", sa.Float(), nullable=True),
        "unidade_esquerda": sa.Column("unidade_esquerda", sa.String(), nullable=True),
        "unidade_direita": sa.Column("unidade_direita", sa.String(), nullable=True),
        "assimetria_percentual": sa.Column("assimetria_percentual", sa.Float(), nullable=True),
        "lateralidade": sa.Column("lateralidade", sa.String(), nullable=False, server_default="bilateral"),
        "medicao_id": sa.Column("medicao_id", sa.String(length=36), nullable=True),
        "definicao_id": sa.Column("definicao_id", sa.Integer(), sa.ForeignKey("definicoes_testes_fisicos.id", ondelete="SET NULL"), nullable=True),
    }
    for nome, coluna in novas.items():
        if nome not in colunas:
            op.add_column("testes_fisicos", coluna)
    op.create_index("ix_testes_fisicos_medicao_id", "testes_fisicos", ["medicao_id"], unique=False)
    op.create_index("ix_testes_fisicos_definicao_id", "testes_fisicos", ["definicao_id"], unique=False)


def downgrade() -> None:
    for indice in ("ix_testes_fisicos_definicao_id", "ix_testes_fisicos_medicao_id"):
        op.drop_index(indice, table_name="testes_fisicos")
    for coluna in ("definicao_id", "medicao_id", "lateralidade", "assimetria_percentual", "unidade_direita", "unidade_esquerda", "resultado_direito", "resultado_esquerdo"):
        op.drop_column("testes_fisicos", coluna)
    op.drop_table("definicoes_testes_fisicos")

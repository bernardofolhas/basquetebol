"""Adiciona o mapa anual de conteudos e as respetivas prioridades."""

import sqlalchemy as sa
from alembic import op


revision = "0025_mapa_conteudos"
down_revision = "0024_origem_setplay"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tabelas = set(inspector.get_table_names())

    if "conteudos_mapa_anual" not in tabelas:
        op.create_table(
            "conteudos_mapa_anual",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("clube_id", sa.Integer(), sa.ForeignKey("clubes.id", ondelete="CASCADE"), nullable=False),
            sa.Column("codigo", sa.String(length=100), nullable=False),
            sa.Column("area", sa.String(length=80), nullable=False),
            sa.Column("subarea", sa.String(length=100), nullable=True),
            sa.Column("nome", sa.String(length=180), nullable=False),
            sa.Column("ordem_area", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("ordem_subarea", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("ordem", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("criado_em", sa.DateTime(), nullable=False),
            sa.Column("atualizado_em", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("clube_id", "codigo", name="uq_conteudo_mapa_clube_codigo"),
        )
        op.create_index("ix_conteudos_mapa_anual_id", "conteudos_mapa_anual", ["id"])
        op.create_index("ix_conteudos_mapa_anual_clube_id", "conteudos_mapa_anual", ["clube_id"])

    if "prioridades_conteudos_mapa_anual" not in tabelas:
        op.create_table(
            "prioridades_conteudos_mapa_anual",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("clube_id", sa.Integer(), sa.ForeignKey("clubes.id", ondelete="CASCADE"), nullable=False),
            sa.Column(
                "planeamento_anual_id",
                sa.Integer(),
                sa.ForeignKey("planeamentos_anuais_equipa.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "conteudo_id",
                sa.Integer(),
                sa.ForeignKey("conteudos_mapa_anual.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "microciclo_id",
                sa.Integer(),
                sa.ForeignKey("microciclos.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("semana_inicio", sa.Date(), nullable=False),
            sa.Column("prioridade", sa.Integer(), nullable=False),
            sa.Column("criado_em", sa.DateTime(), nullable=False),
            sa.Column("atualizado_em", sa.DateTime(), nullable=False),
            sa.CheckConstraint("prioridade IN (1, 2)", name="ck_prioridade_mapa_anual_valor"),
            sa.UniqueConstraint(
                "planeamento_anual_id",
                "conteudo_id",
                "semana_inicio",
                name="uq_prioridade_mapa_anual_semana",
            ),
        )
        op.create_index(
            "ix_prioridades_conteudos_mapa_anual_id",
            "prioridades_conteudos_mapa_anual",
            ["id"],
        )
        op.create_index(
            "ix_prioridades_conteudos_mapa_anual_clube_id",
            "prioridades_conteudos_mapa_anual",
            ["clube_id"],
        )
        op.create_index(
            "ix_prioridades_conteudos_mapa_anual_planeamento_anual_id",
            "prioridades_conteudos_mapa_anual",
            ["planeamento_anual_id"],
        )
        op.create_index(
            "ix_prioridades_conteudos_mapa_anual_conteudo_id",
            "prioridades_conteudos_mapa_anual",
            ["conteudo_id"],
        )
        op.create_index(
            "ix_prioridades_conteudos_mapa_anual_microciclo_id",
            "prioridades_conteudos_mapa_anual",
            ["microciclo_id"],
        )
        op.create_index(
            "ix_prioridades_conteudos_mapa_anual_semana_inicio",
            "prioridades_conteudos_mapa_anual",
            ["semana_inicio"],
        )


def downgrade() -> None:
    op.drop_table("prioridades_conteudos_mapa_anual")
    op.drop_table("conteudos_mapa_anual")

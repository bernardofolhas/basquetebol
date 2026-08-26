"""Permite personalizar os conteudos de cada mapa anual."""

import sqlalchemy as sa
from alembic import op


revision = "0026_conteudos_mapa"
down_revision = "0025_mapa_conteudos"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    colunas = {item["name"] for item in inspector.get_columns("conteudos_mapa_anual")}
    if "planeamento_anual_id" not in colunas:
        with op.batch_alter_table("conteudos_mapa_anual") as batch_op:
            batch_op.add_column(sa.Column("planeamento_anual_id", sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                "fk_conteudo_mapa_planeamento_anual",
                "planeamentos_anuais_equipa",
                ["planeamento_anual_id"],
                ["id"],
                ondelete="CASCADE",
            )
            batch_op.create_index(
                "ix_conteudos_mapa_anual_planeamento_anual_id",
                ["planeamento_anual_id"],
            )

    tabelas = set(inspector.get_table_names())
    if "conteudos_mapa_anual_ocultos" not in tabelas:
        op.create_table(
            "conteudos_mapa_anual_ocultos",
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
            sa.Column("criado_em", sa.DateTime(), nullable=False),
            sa.UniqueConstraint(
                "planeamento_anual_id",
                "conteudo_id",
                name="uq_conteudo_mapa_oculto_planeamento",
            ),
        )
        op.create_index("ix_conteudos_mapa_anual_ocultos_id", "conteudos_mapa_anual_ocultos", ["id"])
        op.create_index(
            "ix_conteudos_mapa_anual_ocultos_clube_id",
            "conteudos_mapa_anual_ocultos",
            ["clube_id"],
        )
        op.create_index(
            "ix_conteudos_mapa_anual_ocultos_planeamento_anual_id",
            "conteudos_mapa_anual_ocultos",
            ["planeamento_anual_id"],
        )
        op.create_index(
            "ix_conteudos_mapa_anual_ocultos_conteudo_id",
            "conteudos_mapa_anual_ocultos",
            ["conteudo_id"],
        )


def downgrade() -> None:
    op.drop_table("conteudos_mapa_anual_ocultos")
    with op.batch_alter_table("conteudos_mapa_anual") as batch_op:
        batch_op.drop_index("ix_conteudos_mapa_anual_planeamento_anual_id")
        batch_op.drop_constraint("fk_conteudo_mapa_planeamento_anual", type_="foreignkey")
        batch_op.drop_column("planeamento_anual_id")

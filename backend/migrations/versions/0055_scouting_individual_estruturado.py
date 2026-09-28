"""Estrutura avaliações, tendências e game plan do scouting individual."""

from alembic import op
import sqlalchemy as sa


revision = "0055_scouting_individual"
down_revision = "0054_testes_fisicos_plano"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scouting_grupos_avaliacao",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("clube_id", sa.Integer(), sa.ForeignKey("clubes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("nome", sa.String(length=120), nullable=False),
        sa.Column("nome_normalizado", sa.String(length=120), nullable=False),
        sa.Column("ordem", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("clube_id", "nome_normalizado", name="uq_scouting_grupo_avaliacao_clube_nome"),
    )
    op.create_index("ix_scouting_grupos_avaliacao_clube_id", "scouting_grupos_avaliacao", ["clube_id"])

    with op.batch_alter_table("scouting_biblioteca_itens") as batch:
        batch.add_column(sa.Column("grupo_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("ordem", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()))
        batch.create_foreign_key(
            "fk_scouting_biblioteca_itens_grupo_id",
            "scouting_grupos_avaliacao",
            ["grupo_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index("ix_scouting_biblioteca_itens_grupo_id", ["grupo_id"])

    with op.batch_alter_table("scouting_jogadores_itens") as batch:
        batch.add_column(sa.Column("avaliacao", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("prioridade", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("ordem", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("destaque", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("ordem_destaque", sa.Integer(), nullable=True))
        batch.create_check_constraint(
            "ck_scouting_jogador_item_avaliacao",
            "avaliacao IS NULL OR (avaliacao >= 1 AND avaliacao <= 5)",
        )
        batch.create_check_constraint(
            "ck_scouting_jogador_item_prioridade",
            "prioridade IS NULL OR (prioridade >= 1 AND prioridade <= 3)",
        )


def downgrade() -> None:
    with op.batch_alter_table("scouting_jogadores_itens") as batch:
        batch.drop_constraint("ck_scouting_jogador_item_prioridade", type_="check")
        batch.drop_constraint("ck_scouting_jogador_item_avaliacao", type_="check")
        batch.drop_column("ordem_destaque")
        batch.drop_column("destaque")
        batch.drop_column("ordem")
        batch.drop_column("prioridade")
        batch.drop_column("avaliacao")

    with op.batch_alter_table("scouting_biblioteca_itens") as batch:
        batch.drop_index("ix_scouting_biblioteca_itens_grupo_id")
        batch.drop_constraint("fk_scouting_biblioteca_itens_grupo_id", type_="foreignkey")
        batch.drop_column("ativo")
        batch.drop_column("ordem")
        batch.drop_column("grupo_id")

    op.drop_table("scouting_grupos_avaliacao")

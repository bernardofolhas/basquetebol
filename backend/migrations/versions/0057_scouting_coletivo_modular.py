"""Adiciona blocos estruturados ao scouting coletivo."""

from alembic import op
import sqlalchemy as sa


revision = "0057_scouting_coletivo_modular"
down_revision = "0056_simbolo_adversario"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspetor = sa.inspect(op.get_bind())
    colunas = {coluna["name"] for coluna in inspetor.get_columns("predefinicoes_relatorios")}
    if "configuracao" not in colunas:
        op.add_column("predefinicoes_relatorios", sa.Column("configuracao", sa.Text(), nullable=True))
    if "scouting_blocos_coletivos" in inspetor.get_table_names():
        return
    op.create_table(
        "scouting_blocos_coletivos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("clube_id", sa.Integer(), sa.ForeignKey("clubes.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("adversario_id", sa.Integer(), sa.ForeignKey("scouting_adversarios.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("jogo_id", sa.Integer(), sa.ForeignKey("jogos.id", ondelete="CASCADE"), nullable=True, index=True),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("scouting_biblioteca_itens.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("tipo", sa.String(32), nullable=False, index=True),
        sa.Column("categoria", sa.String(64)),
        sa.Column("titulo", sa.String(160), nullable=False),
        sa.Column("descricao", sa.Text()),
        sa.Column("nivel", sa.String(16)),
        sa.Column("prioridade", sa.Integer()),
        sa.Column("ordem", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("destaque", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(), nullable=False),
        sa.CheckConstraint("nivel IS NULL OR nivel IN ('fraco','medio','forte')", name="ck_scouting_bloco_coletivo_nivel"),
        sa.CheckConstraint("prioridade IS NULL OR (prioridade >= 1 AND prioridade <= 3)", name="ck_scouting_bloco_coletivo_prioridade"),
    )


def downgrade() -> None:
    op.drop_table("scouting_blocos_coletivos")
    op.drop_column("predefinicoes_relatorios", "configuracao")

"""Adiciona scouting de adversários e auto-scouting por jogo."""

import sqlalchemy as sa
from alembic import op


revision = "0027_scouting"
down_revision = "0026_conteudos_mapa"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tabelas = set(inspector.get_table_names())
    if "relatorios_scouting" not in tabelas:
        op.create_table(
            "relatorios_scouting",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("clube_id", sa.Integer(), sa.ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("jogo_id", sa.Integer(), sa.ForeignKey("jogos.id", ondelete="CASCADE"), nullable=False, unique=True),
            sa.Column("estado", sa.String(length=24), nullable=False, server_default="rascunho"),
            sa.Column("jogos_observados", sa.String(length=120)), sa.Column("fontes", sa.Text()), sa.Column("confianca", sa.String(length=24)),
            sa.Column("identidade", sa.Text()), sa.Column("pontos_fortes", sa.Text()), sa.Column("vulnerabilidades", sa.Text()),
            sa.Column("ataque", sa.Text()), sa.Column("defesa", sa.Text()), sa.Column("transicao", sa.Text()), sa.Column("situacoes_especiais", sa.Text()),
            sa.Column("prioridades_defensivas", sa.Text()), sa.Column("prioridades_ofensivas", sa.Text()), sa.Column("primeiros_minutos", sa.Text()), sa.Column("plano_contingencia", sa.Text()),
            sa.Column("auto_scouting", sa.Text()), sa.Column("melhorias_prioritarias", sa.Text()),
            sa.Column("criado_em", sa.DateTime(), nullable=False), sa.Column("atualizado_em", sa.DateTime(), nullable=False), sa.Column("publicado_em", sa.DateTime()),
        )
        op.create_index("ix_relatorios_scouting_clube_id", "relatorios_scouting", ["clube_id"])
        op.create_index("ix_relatorios_scouting_jogo_id", "relatorios_scouting", ["jogo_id"])
    for tabela, campos in {
        "scouting_jogadores_adversarios": [
            sa.Column("id", sa.Integer(), primary_key=True), sa.Column("clube_id", sa.Integer(), sa.ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("relatorio_id", sa.Integer(), sa.ForeignKey("relatorios_scouting.id", ondelete="CASCADE"), nullable=False), sa.Column("ordem", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("numero", sa.String(length=12)), sa.Column("nome", sa.String(length=160), nullable=False), sa.Column("posicao", sa.String(length=48)), sa.Column("papel", sa.String(length=100)), sa.Column("mao_dominante", sa.String(length=24)),
            sa.Column("como_pontua", sa.Text()), sa.Column("tendencias", sa.Text()), sa.Column("pontos_fortes", sa.Text()), sa.Column("limitacoes", sa.Text()), sa.Column("como_defender", sa.Text()), sa.Column("como_atacar", sa.Text()), sa.Column("prioridade", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("partilhavel", sa.Boolean(), nullable=False, server_default=sa.true()),
        ],
        "scouting_acoes": [
            sa.Column("id", sa.Integer(), primary_key=True), sa.Column("clube_id", sa.Integer(), sa.ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("relatorio_id", sa.Integer(), sa.ForeignKey("relatorios_scouting.id", ondelete="CASCADE"), nullable=False), sa.Column("ordem", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("categoria", sa.String(length=64), nullable=False, server_default="Ataque"), sa.Column("nome", sa.String(length=160), nullable=False), sa.Column("descricao", sa.Text()), sa.Column("resposta", sa.Text()), sa.Column("prioridade", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("partilhavel", sa.Boolean(), nullable=False, server_default=sa.true()),
        ],
    }.items():
        if tabela not in tabelas:
            op.create_table(tabela, *campos)
            op.create_index(f"ix_{tabela}_clube_id", tabela, ["clube_id"])
            op.create_index(f"ix_{tabela}_relatorio_id", tabela, ["relatorio_id"])


def downgrade() -> None:
    op.drop_table("scouting_acoes")
    op.drop_table("scouting_jogadores_adversarios")
    op.drop_table("relatorios_scouting")

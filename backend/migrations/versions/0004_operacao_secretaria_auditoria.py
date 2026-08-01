"""Adds reusable exercise tags, player documents, audit and planning history."""

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy import inspect


revision = "0004_secretaria_auditoria"
down_revision = "0003_assiduidade_estado"
branch_labels = None
depends_on = None


def _criar_tabelas() -> None:
    op.create_table(
        "documentos_jogadores",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("jogador_id", sa.Integer(), sa.ForeignKey("jogadores.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tipo", sa.String(), nullable=False),
        sa.Column("nome", sa.String(), nullable=False),
        sa.Column("data_documento", sa.Date(), nullable=True),
        sa.Column("validade", sa.Date(), nullable=True),
        sa.Column("estado", sa.String(), nullable=False, server_default="pendente"),
        sa.Column("observacoes", sa.Text(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "registos_auditoria",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.Column("utilizador_id", sa.Integer(), sa.ForeignKey("utilizadores.id", ondelete="SET NULL"), nullable=True),
        sa.Column("utilizador_username", sa.String(), nullable=True),
        sa.Column("acao", sa.String(), nullable=False),
        sa.Column("entidade", sa.String(), nullable=False),
        sa.Column("entidade_id", sa.Integer(), nullable=True),
        sa.Column("detalhes", sa.Text(), nullable=True),
        sa.Column("endereco_ip", sa.String(), nullable=True),
    )
    op.create_table(
        "historico_planeamento_clube",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.Column("utilizador_id", sa.Integer(), sa.ForeignKey("utilizadores.id", ondelete="SET NULL"), nullable=True),
        sa.Column("utilizador_username", sa.String(), nullable=True),
        sa.Column("entidade", sa.String(), nullable=False),
        sa.Column("entidade_id", sa.Integer(), nullable=False),
        sa.Column("acao", sa.String(), nullable=False),
        sa.Column("detalhes", sa.Text(), nullable=True),
    )


def upgrade() -> None:
    if context.is_offline_mode():
        op.add_column("biblioteca_exercicios", sa.Column("tags", sa.String(), nullable=True))
        _criar_tabelas()
        return

    bind = op.get_bind()
    tabelas = set(inspect(bind).get_table_names())
    if "biblioteca_exercicios" in tabelas:
        colunas = {coluna["name"] for coluna in inspect(bind).get_columns("biblioteca_exercicios")}
        if "tags" not in colunas:
            op.add_column("biblioteca_exercicios", sa.Column("tags", sa.String(), nullable=True))
    if "documentos_jogadores" not in tabelas:
        _criar_tabelas()


def downgrade() -> None:
    if context.is_offline_mode():
        op.drop_table("historico_planeamento_clube")
        op.drop_table("registos_auditoria")
        op.drop_table("documentos_jogadores")
        op.drop_column("biblioteca_exercicios", "tags")
        return

    bind = op.get_bind()
    tabelas = set(inspect(bind).get_table_names())
    for nome in ("historico_planeamento_clube", "registos_auditoria", "documentos_jogadores"):
        if nome in tabelas:
            op.drop_table(nome)
    if "biblioteca_exercicios" in tabelas:
        colunas = {coluna["name"] for coluna in inspect(bind).get_columns("biblioteca_exercicios")}
        if "tags" in colunas:
            op.drop_column("biblioteca_exercicios", "tags")

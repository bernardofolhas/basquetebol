"""Add configurable club identity used by the web app and PDFs."""

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy import inspect


revision = "0005_identidade_clube"
down_revision = "0004_secretaria_auditoria"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if context.is_offline_mode():
        _criar_tabela()
        return

    if "identidade_clube" in inspect(op.get_bind()).get_table_names():
        return
    _criar_tabela()


def _criar_tabela() -> None:
    op.create_table(
        "identidade_clube",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("nome_oficial", sa.String(), nullable=False, server_default="Clube de Basquetebol"),
        sa.Column("nome_curto", sa.String(), nullable=True),
        sa.Column("logo_principal", sa.String(), nullable=True),
        sa.Column("logo_secundario", sa.String(), nullable=True),
        sa.Column("cor_principal", sa.String(), nullable=False, server_default="#f97316"),
        sa.Column("cor_secundaria", sa.String(), nullable=False, server_default="#1f2937"),
        sa.Column("cor_destaque", sa.String(), nullable=False, server_default="#0ea5e9"),
        sa.Column("texto_rodape", sa.Text(), nullable=True),
        sa.Column("epoca_predefinida", sa.String(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    if context.is_offline_mode():
        op.drop_table("identidade_clube")
        return
    if "identidade_clube" in inspect(op.get_bind()).get_table_names():
        op.drop_table("identidade_clube")

"""Adiciona metadados e mapeamentos para importação FIBA LiveStats."""

import sqlalchemy as sa
from alembic import op


revision = "0032_importacao_fiba"
down_revision = "0031_posicao_estatistica"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    colunas = {coluna["name"] for coluna in inspector.get_columns("eventos_estatistica")}
    novas_colunas = {
        "origem": sa.Column("origem", sa.String(length=24), nullable=False, server_default="manual"),
        "identificador_externo": sa.Column("identificador_externo", sa.String(length=160), nullable=True),
        "jogador_externo": sa.Column("jogador_externo", sa.String(length=120), nullable=True),
        "subtipo": sa.Column("subtipo", sa.String(length=60), nullable=True),
        "qualificadores": sa.Column("qualificadores", sa.Text(), nullable=True),
        "importacao_uid": sa.Column("importacao_uid", sa.String(length=80), nullable=True),
    }
    for nome, coluna in novas_colunas.items():
        if nome not in colunas:
            op.add_column("eventos_estatistica", coluna)

    indices = {indice["name"] for indice in inspector.get_indexes("eventos_estatistica")}
    for nome in ("origem", "importacao_uid"):
        indice = f"ix_eventos_estatistica_{nome}"
        if indice not in indices:
            op.create_index(indice, "eventos_estatistica", [nome])

    if "mapeamentos_jogadores_estatistica" not in inspector.get_table_names():
        op.create_table(
            "mapeamentos_jogadores_estatistica",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("clube_id", sa.Integer(), sa.ForeignKey("clubes.id", ondelete="CASCADE"), nullable=False),
            sa.Column("equipa_id", sa.Integer(), sa.ForeignKey("equipas.id", ondelete="CASCADE"), nullable=False),
            sa.Column("jogador_id", sa.Integer(), sa.ForeignKey("jogadores.id", ondelete="CASCADE"), nullable=False),
            sa.Column("fornecedor", sa.String(length=24), nullable=False, server_default="fiba"),
            sa.Column("identificador_externo", sa.String(length=120), nullable=False),
            sa.Column("nome_externo", sa.String(length=160), nullable=True),
            sa.Column("numero_externo", sa.String(length=16), nullable=True),
            sa.Column("criado_em", sa.DateTime(), nullable=False),
            sa.Column("atualizado_em", sa.DateTime(), nullable=False),
            sa.UniqueConstraint(
                "equipa_id",
                "fornecedor",
                "identificador_externo",
                name="uq_mapeamento_estatistica_equipa_fornecedor_externo",
            ),
        )
        for nome in ("clube_id", "equipa_id", "jogador_id"):
            op.create_index(
                f"ix_mapeamentos_jogadores_estatistica_{nome}",
                "mapeamentos_jogadores_estatistica",
                [nome],
            )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "mapeamentos_jogadores_estatistica" in inspector.get_table_names():
        op.drop_table("mapeamentos_jogadores_estatistica")
    colunas = {coluna["name"] for coluna in inspector.get_columns("eventos_estatistica")}
    for nome in ("importacao_uid", "qualificadores", "subtipo", "jogador_externo", "identificador_externo", "origem"):
        if nome in colunas:
            op.drop_column("eventos_estatistica", nome)

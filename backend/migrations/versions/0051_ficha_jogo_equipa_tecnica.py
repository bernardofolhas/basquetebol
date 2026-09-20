"""Adiciona campos para equipa técnica e ficha de jogo."""

from alembic import op
import sqlalchemy as sa


revision = "0051_ficha_jogo_equipa_tecnica"
down_revision = "0050_predefinicoes_relatorios"
branch_labels = None
depends_on = None


def _colunas(tabela: str) -> set[str]:
    return {coluna["name"] for coluna in sa.inspect(op.get_bind()).get_columns(tabela)}


def upgrade() -> None:
    if "numero_licenca_fpb" not in _colunas("jogadores"):
        op.add_column("jogadores", sa.Column("numero_licenca_fpb", sa.String(), nullable=True))
    if "funcao" not in _colunas("treinadores"):
        op.add_column(
            "treinadores",
            sa.Column("funcao", sa.String(), nullable=False, server_default="Treinador"),
        )
    if "numero_jogo" not in _colunas("jogos"):
        op.add_column("jogos", sa.Column("numero_jogo", sa.String(), nullable=True))


def downgrade() -> None:
    for tabela, coluna in (("jogos", "numero_jogo"), ("treinadores", "funcao"), ("jogadores", "numero_licenca_fpb")):
        if coluna in _colunas(tabela):
            op.drop_column(tabela, coluna)

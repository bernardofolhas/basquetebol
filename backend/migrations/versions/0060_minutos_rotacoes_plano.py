"""Guarda o minuto previsto das três rotações do plano de jogo."""

from alembic import op
import sqlalchemy as sa


revision = "0060_minutos_rotacoes_plano"
down_revision = "0059_substituicoes_previstas"
branch_labels = None
depends_on = None


def upgrade() -> None:
    colunas = {coluna["name"] for coluna in sa.inspect(op.get_bind()).get_columns("planos_jogo")}
    for grupo in range(1, 4):
        nome = f"rotacao_{grupo}_minuto"
        if nome not in colunas:
            op.add_column("planos_jogo", sa.Column(nome, sa.Integer(), nullable=True))


def downgrade() -> None:
    for grupo in range(3, 0, -1):
        op.drop_column("planos_jogo", f"rotacao_{grupo}_minuto")

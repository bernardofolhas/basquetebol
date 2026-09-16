"""Cria o departamento de scouting permanente por adversário."""

from alembic import op
import sqlalchemy as sa


revision = "0047_departamento_scouting"
down_revision = "0046_posicao_secundaria"
branch_labels = None
depends_on = None

TABELAS = {
    "scouting_adversarios", "scouting_adversarios_jogos", "scouting_roster_jogadores",
    "scouting_fichas_individuais", "scouting_medias_epoca", "scouting_estatisticas_jogo",
    "scouting_biblioteca_itens", "scouting_jogadores_itens", "scouting_zonas_acao",
}


def _tenant_columns():
    return [
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("clube_id", sa.Integer(), sa.ForeignKey("clubes.id", ondelete="CASCADE"), nullable=False, index=True),
    ]


def _stats():
    return [sa.Column(nome, sa.Float(), nullable=True) for nome in (
        "minutos", "pontos", "fg_c", "fg_t", "dois_c", "dois_t", "tres_c", "tres_t", "ll_c", "ll_t",
        "ress_of", "ress_def", "ress_total", "assistencias", "faltas", "turnovers", "roubos", "desarmes",
        "mais_menos", "eficiencia",
    )]


def upgrade() -> None:
    try:
        existentes = set(sa.inspect(op.get_bind()).get_table_names())
    except sa.exc.NoInspectionAvailable:
        existentes = set()
    if TABELAS.issubset(existentes):
        return
    if TABELAS & existentes:
        raise RuntimeError("A estrutura do departamento de scouting está apenas parcialmente criada.")
    op.create_table("scouting_adversarios", *_tenant_columns(),
        sa.Column("nome", sa.String(160), nullable=False), sa.Column("nome_normalizado", sa.String(160), nullable=False),
        sa.Column("observacoes", sa.Text()), sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("clube_id", "nome_normalizado", name="uq_scouting_adversario_clube_nome"))
    op.create_table("scouting_adversarios_jogos", *_tenant_columns(),
        sa.Column("adversario_id", sa.Integer(), sa.ForeignKey("scouting_adversarios.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("jogo_id", sa.Integer(), sa.ForeignKey("jogos.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("criado_em", sa.DateTime(), nullable=False), sa.UniqueConstraint("jogo_id", name="uq_scouting_adversario_jogo"))
    op.create_table("scouting_roster_jogadores", *_tenant_columns(),
        sa.Column("adversario_id", sa.Integer(), sa.ForeignKey("scouting_adversarios.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("fotografia", sa.String(300)), sa.Column("nome", sa.String(160), nullable=False), sa.Column("numero", sa.String(12)),
        sa.Column("idade", sa.Integer()), sa.Column("posicao_principal", sa.String(24), nullable=False),
        sa.Column("posicao_alternativa", sa.String(24)), sa.Column("altura_cm", sa.Float()), sa.Column("peso_kg", sa.Float()),
        sa.Column("equipa_anterior", sa.String(160)), sa.Column("estado", sa.String(24), nullable=False),
        sa.Column("mao_dominante", sa.String(24)), sa.Column("observacoes", sa.Text()),
        sa.Column("criado_em", sa.DateTime(), nullable=False), sa.Column("atualizado_em", sa.DateTime(), nullable=False))
    op.create_table("scouting_fichas_individuais", *_tenant_columns(),
        sa.Column("jogador_id", sa.Integer(), sa.ForeignKey("scouting_roster_jogadores.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("resumo", sa.Text()), sa.Column("atualizado_em", sa.DateTime(), nullable=False))
    op.create_table("scouting_medias_epoca", *_tenant_columns(),
        sa.Column("jogador_id", sa.Integer(), sa.ForeignKey("scouting_roster_jogadores.id", ondelete="CASCADE"), nullable=False, unique=True), *_stats())
    op.create_table("scouting_estatisticas_jogo", *_tenant_columns(),
        sa.Column("jogador_id", sa.Integer(), sa.ForeignKey("scouting_roster_jogadores.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("jogo_id", sa.Integer(), sa.ForeignKey("jogos.id", ondelete="SET NULL"), index=True),
        sa.Column("data", sa.Date(), nullable=False), sa.Column("adversario", sa.String(160)), sa.Column("competicao", sa.String(160)), *_stats(),
        sa.UniqueConstraint("jogador_id", "jogo_id", name="uq_scouting_estatistica_jogador_jogo"))
    op.create_table("scouting_biblioteca_itens", *_tenant_columns(), sa.Column("categoria", sa.String(32), nullable=False, index=True),
        sa.Column("nome", sa.String(160), nullable=False), sa.Column("nome_normalizado", sa.String(160), nullable=False),
        sa.UniqueConstraint("clube_id", "categoria", "nome_normalizado", name="uq_scouting_biblioteca_item"))
    op.create_table("scouting_jogadores_itens", *_tenant_columns(),
        sa.Column("jogador_id", sa.Integer(), sa.ForeignKey("scouting_roster_jogadores.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("scouting_biblioteca_itens.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("observacao", sa.Text()), sa.UniqueConstraint("jogador_id", "item_id", name="uq_scouting_jogador_item"))
    op.create_table("scouting_zonas_acao", *_tenant_columns(),
        sa.Column("jogador_id", sa.Integer(), sa.ForeignKey("scouting_roster_jogadores.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("zona", sa.String(48), nullable=False), sa.Column("observacao", sa.Text()),
        sa.UniqueConstraint("jogador_id", "zona", name="uq_scouting_jogador_zona"))


def downgrade() -> None:
    try:
        existentes = set(sa.inspect(op.get_bind()).get_table_names())
    except sa.exc.NoInspectionAvailable:
        existentes = set(TABELAS)
    for tabela in ("scouting_zonas_acao", "scouting_jogadores_itens", "scouting_biblioteca_itens", "scouting_estatisticas_jogo", "scouting_medias_epoca", "scouting_fichas_individuais", "scouting_roster_jogadores", "scouting_adversarios_jogos", "scouting_adversarios"):
        if tabela in existentes:
            op.drop_table(tabela)

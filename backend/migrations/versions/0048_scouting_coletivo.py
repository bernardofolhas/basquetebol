"""Implementa dados estatísticos, técnico-táticos e playbook do scouting coletivo."""

from alembic import op
import sqlalchemy as sa


revision = "0048_scouting_coletivo"
down_revision = "0047_departamento_scouting"
branch_labels = None
depends_on = None

TABELAS = (
    "scouting_resultados_coletivos", "scouting_medias_coletivas",
    "scouting_estatisticas_coletivas_jogo", "scouting_adversarios_itens",
    "scouting_lideres_estatisticos", "scouting_opcoes_defensivas",
    "scouting_conceitos_ofensivos", "scouting_momentos_playbook",
)
STAT_FIELDS = (
    "minutos", "pontos", "fg_c", "fg_t", "dois_c", "dois_t", "tres_c", "tres_t", "ll_c", "ll_t",
    "ress_of", "ress_def", "ress_total", "assistencias", "faltas", "turnovers", "roubos", "desarmes",
    "mais_menos", "eficiencia",
)


def _base():
    return [sa.Column("id", sa.Integer(), primary_key=True), sa.Column("clube_id", sa.Integer(), sa.ForeignKey("clubes.id", ondelete="CASCADE"), nullable=False, index=True)]


def _stats():
    return [sa.Column(nome, sa.Float()) for nome in STAT_FIELDS]


def upgrade() -> None:
    try:
        existentes = set(sa.inspect(op.get_bind()).get_table_names())
    except sa.exc.NoInspectionAvailable:
        existentes = set()
    if set(TABELAS).issubset(existentes):
        return
    if set(TABELAS) & existentes:
        raise RuntimeError("A estrutura do scouting coletivo está apenas parcialmente criada.")
    op.create_table("scouting_resultados_coletivos", *_base(),
        sa.Column("adversario_id", sa.Integer(), sa.ForeignKey("scouting_adversarios.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("jogo_id", sa.Integer(), sa.ForeignKey("jogos.id", ondelete="SET NULL"), index=True),
        sa.Column("data", sa.Date(), nullable=False), sa.Column("oponente", sa.String(160), nullable=False),
        sa.Column("em_casa", sa.Boolean(), nullable=False), sa.Column("pontos_marcados", sa.Integer()),
        sa.Column("pontos_sofridos", sa.Integer()), sa.Column("competicao", sa.String(160)),
        sa.UniqueConstraint("adversario_id", "jogo_id", name="uq_scouting_resultado_jogo"))
    op.create_table("scouting_medias_coletivas", *_base(),
        sa.Column("adversario_id", sa.Integer(), sa.ForeignKey("scouting_adversarios.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("usar_manual", sa.Boolean(), nullable=False), *_stats())
    op.create_table("scouting_estatisticas_coletivas_jogo", *_base(),
        sa.Column("adversario_id", sa.Integer(), sa.ForeignKey("scouting_adversarios.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("resultado_id", sa.Integer(), sa.ForeignKey("scouting_resultados_coletivos.id", ondelete="CASCADE"), index=True),
        sa.Column("data", sa.Date(), nullable=False), *_stats(),
        sa.UniqueConstraint("adversario_id", "resultado_id", name="uq_scouting_estatistica_coletiva_resultado"))
    op.create_table("scouting_adversarios_itens", *_base(),
        sa.Column("adversario_id", sa.Integer(), sa.ForeignKey("scouting_adversarios.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("scouting_biblioteca_itens.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("observacao", sa.Text()), sa.Column("valor", sa.String(80)), sa.Column("ranking", sa.String(80)),
        sa.Column("validade", sa.String(120)), sa.UniqueConstraint("adversario_id", "item_id", name="uq_scouting_adversario_item"))
    op.create_table("scouting_lideres_estatisticos", *_base(),
        sa.Column("adversario_id", sa.Integer(), sa.ForeignKey("scouting_adversarios.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("jogador_id", sa.Integer(), sa.ForeignKey("scouting_roster_jogadores.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("tipo", sa.String(120), nullable=False), sa.Column("observacao", sa.Text()))
    op.create_table("scouting_opcoes_defensivas", *_base(),
        sa.Column("adversario_id", sa.Integer(), sa.ForeignKey("scouting_adversarios.id", ondelete="CASCADE"), nullable=False, unique=True),
        *[coluna for nome in ("bloqueio_central", "bloqueio_lateral", "bloqueio_indireto", "handoff", "bola_interior", "alteracoes")
          for coluna in (sa.Column(nome, sa.Boolean(), nullable=False), sa.Column(f"{nome}_notas", sa.Text()))])
    for tabela in ("scouting_conceitos_ofensivos", "scouting_momentos_playbook"):
        op.create_table(tabela, *_base(),
            sa.Column("adversario_id", sa.Integer(), sa.ForeignKey("scouting_adversarios.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("setplay_id", sa.Integer(), sa.ForeignKey("setplays.id", ondelete="CASCADE"), nullable=False, unique=True, index=True),
            sa.Column("ordem", sa.Integer(), nullable=False))


def downgrade() -> None:
    try:
        existentes = set(sa.inspect(op.get_bind()).get_table_names())
    except sa.exc.NoInspectionAvailable:
        existentes = set(TABELAS)
    for tabela in reversed(TABELAS):
        if tabela in existentes:
            op.drop_table(tabela)

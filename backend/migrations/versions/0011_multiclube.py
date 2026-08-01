"""Cria clubes e associa os dados existentes ao clube inicial."""

import sqlalchemy as sa
from alembic import op

revision = "0011_multiclube"
down_revision = "0010_eventos_blocos"
branch_labels = None
depends_on = None


TABELAS_DIRETAS = (
    "utilizadores", "equipas", "treinadores", "jogadores", "jogos",
    "atividades", "espacos_treino", "identidade_clube", "registos_auditoria",
    "macrociclos", "planeamentos_clube_anuais", "eventos_planeamento_clube",
    "biblioteca_exercicios",
)


def _colunas(inspector, tabela):
    return {coluna["name"] for coluna in inspector.get_columns(tabela)}


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        bind.execute(sa.text("ALTER TYPE perfilenum ADD VALUE IF NOT EXISTS 'superadministrador'"))
    inspector = sa.inspect(bind)
    if not inspector.has_table("clubes"):
        op.create_table(
            "clubes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("nome_oficial", sa.String(), nullable=False),
            sa.Column("nome_curto", sa.String(), nullable=False),
            sa.Column("identificador", sa.String(), nullable=False, unique=True),
            sa.Column("logo_principal", sa.String(), nullable=True),
            sa.Column("cor_principal", sa.String(), nullable=False, server_default="#f97316"),
            sa.Column("cor_secundaria", sa.String(), nullable=False, server_default="#1f2937"),
            sa.Column("cor_destaque", sa.String(), nullable=False, server_default="#0ea5e9"),
            sa.Column("tema_gerado", sa.Text(), nullable=True),
            sa.Column("estado", sa.String(), nullable=False, server_default="ativo"),
            sa.Column("epoca_inicial", sa.String(), nullable=True),
            sa.Column("administrador_principal_id", sa.Integer(), nullable=True),
            sa.Column("criado_em", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("atualizado_em", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_clubes_identificador", "clubes", ["identificador"], unique=True)

    identidade = None
    if inspector.has_table("identidade_clube"):
        identidade = bind.execute(sa.text(
            "SELECT nome_oficial, nome_curto, logo_principal, cor_principal, cor_secundaria, "
            "cor_destaque, epoca_predefinida FROM identidade_clube ORDER BY id LIMIT 1"
        )).mappings().first()
    existe = bind.execute(sa.text("SELECT id FROM clubes ORDER BY id LIMIT 1")).scalar()
    if not existe:
        dados = dict(identidade or {})
        bind.execute(sa.text(
            "INSERT INTO clubes (nome_oficial,nome_curto,identificador,logo_principal,cor_principal,cor_secundaria,cor_destaque,estado,epoca_inicial,criado_em,atualizado_em) "
            "VALUES (:nome_oficial,:nome_curto,'clube-inicial',:logo,:principal,:secundaria,:destaque,'ativo',:epoca,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
        ), {
            "nome_oficial": dados.get("nome_oficial") or "Clube de Basquetebol",
            "nome_curto": dados.get("nome_curto") or dados.get("nome_oficial") or "Clube",
            "logo": dados.get("logo_principal"), "principal": dados.get("cor_principal") or "#f97316",
            "secundaria": dados.get("cor_secundaria") or "#1f2937",
            "destaque": dados.get("cor_destaque") or "#0ea5e9", "epoca": dados.get("epoca_predefinida"),
        })
    clube_id = bind.execute(sa.text("SELECT id FROM clubes ORDER BY id LIMIT 1")).scalar_one()

    inspector = sa.inspect(bind)
    for tabela in TABELAS_DIRETAS:
        if not inspector.has_table(tabela):
            continue
        if "clube_id" not in _colunas(inspector, tabela):
            op.add_column(tabela, sa.Column("clube_id", sa.Integer(), nullable=True))
        bind.execute(sa.text(f"UPDATE {tabela} SET clube_id = :id WHERE clube_id IS NULL"), {"id": clube_id})
        indices = {item["name"] for item in sa.inspect(bind).get_indexes(tabela)}
        nome_indice = f"ix_{tabela}_clube_id"
        if nome_indice not in indices:
            op.create_index(nome_indice, tabela, ["clube_id"], unique=(tabela == "identidade_clube"))
        fks = {item.get("name") for item in sa.inspect(bind).get_foreign_keys(tabela)}
        nome_fk = f"fk_{tabela}_clube"
        if nome_fk not in fks:
            op.create_foreign_key(nome_fk, tabela, "clubes", ["clube_id"], ["id"], ondelete="SET NULL" if tabela == "registos_auditoria" else "RESTRICT")
        if tabela != "registos_auditoria":
            op.alter_column(tabela, "clube_id", nullable=False)

    if "deve_alterar_password" not in _colunas(sa.inspect(bind), "utilizadores"):
        op.add_column("utilizadores", sa.Column("deve_alterar_password", sa.Boolean(), nullable=False, server_default=sa.false()))
    admin_id = bind.execute(sa.text("SELECT id FROM utilizadores WHERE perfil = 'administrador' ORDER BY id LIMIT 1")).scalar()
    if admin_id:
        bind.execute(sa.text("UPDATE clubes SET administrador_principal_id=:admin WHERE id=:clube"), {"admin": admin_id, "clube": clube_id})
    fks_clube = {item.get("name") for item in sa.inspect(bind).get_foreign_keys("clubes")}
    if "fk_clube_admin_principal" not in fks_clube:
        op.create_foreign_key("fk_clube_admin_principal", "clubes", "utilizadores", ["administrador_principal_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    raise RuntimeError("A reversão multi-clube é bloqueada para não perder a pertença dos dados.")

"""Isola também recursos consultados diretamente por ID."""

import sqlalchemy as sa
from alembic import op

revision = "0012_isolamento_filhos"
down_revision = "0011_multiclube"
branch_labels = None
depends_on = None


ORIGENS = {
    "mesociclos": "SELECT m.id, ma.clube_id FROM mesociclos m JOIN macrociclos ma ON ma.id=m.macrociclo_id",
    "microciclos": "SELECT mi.id, ma.clube_id FROM microciclos mi JOIN mesociclos me ON me.id=mi.mesociclo_id JOIN macrociclos ma ON ma.id=me.macrociclo_id",
    "sessoes_treino": "SELECT s.id, ma.clube_id FROM sessoes_treino s JOIN microciclos mi ON mi.id=s.microciclo_id JOIN mesociclos me ON me.id=mi.mesociclo_id JOIN macrociclos ma ON ma.id=me.macrociclo_id",
    "planos_treino": "SELECT p.id, s.clube_id FROM planos_treino p JOIN sessoes_treino s ON s.id=p.sessao_id",
    "blocos_treino": "SELECT b.id, p.clube_id FROM blocos_treino b JOIN planos_treino p ON p.id=b.plano_id",
    "exercicios_plano": "SELECT e.id, p.clube_id FROM exercicios_plano e JOIN planos_treino p ON p.id=e.plano_id",
    "convocados": "SELECT c.id, j.clube_id FROM convocados c JOIN jogos j ON j.id=c.jogo_id",
    "planos_jogo": "SELECT p.id, j.clube_id FROM planos_jogo p JOIN jogos j ON j.id=p.jogo_id",
    "assiduidade": "SELECT a.id, j.clube_id FROM assiduidade a JOIN jogadores j ON j.id=a.jogador_id",
    "testes_fisicos": "SELECT t.id, j.clube_id FROM testes_fisicos t JOIN jogadores j ON j.id=t.jogador_id",
    "planeamentos_fisicos": "SELECT p.id, e.clube_id FROM planeamentos_fisicos p JOIN equipas e ON e.id=p.equipa_id",
    "documentos_jogadores": "SELECT d.id, j.clube_id FROM documentos_jogadores d JOIN jogadores j ON j.id=d.jogador_id",
    "registos_antropometricos": "SELECT r.id, j.clube_id FROM registos_antropometricos r JOIN jogadores j ON j.id=r.jogador_id",
    "playbooks": "SELECT p.id, e.clube_id FROM playbooks p JOIN equipas e ON e.id=p.equipa_id",
    "setplays": "SELECT s.id, p.clube_id FROM setplays s JOIN playbooks p ON p.id=s.playbook_id",
    "passos_setplay": "SELECT x.id, s.clube_id FROM passos_setplay x JOIN setplays s ON s.id=x.setplay_id",
    "atribuicoes_espaco_semanais": "SELECT a.id, e.clube_id FROM atribuicoes_espaco_semanais a JOIN espacos_treino e ON e.id=a.espaco_id",
    "agenda_espaco_equipa": "SELECT a.id, e.clube_id FROM agenda_espaco_equipa a JOIN equipas e ON e.id=a.equipa_id",
    "planeamentos_clube_mensais": "SELECT m.id, a.clube_id FROM planeamentos_clube_mensais m JOIN planeamentos_clube_anuais a ON a.id=m.planeamento_anual_id",
    "planos_semanais_clube": "SELECT s.id, a.clube_id FROM planos_semanais_clube s JOIN planeamentos_clube_mensais m ON m.id=s.planeamento_mensal_id JOIN planeamentos_clube_anuais a ON a.id=m.planeamento_anual_id",
}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    inicial = bind.execute(sa.text("SELECT id FROM clubes ORDER BY id LIMIT 1")).scalar_one()
    for tabela, origem in ORIGENS.items():
        if not inspector.has_table(tabela):
            continue
        colunas = {item["name"] for item in sa.inspect(bind).get_columns(tabela)}
        if "clube_id" not in colunas:
            op.add_column(tabela, sa.Column("clube_id", sa.Integer(), nullable=True))
        bind.execute(sa.text(f"UPDATE {tabela} alvo SET clube_id=origem.clube_id FROM ({origem}) origem WHERE alvo.id=origem.id AND alvo.clube_id IS NULL"))
        bind.execute(sa.text(f"UPDATE {tabela} SET clube_id=:clube WHERE clube_id IS NULL"), {"clube": inicial})
        nome_indice = f"ix_{tabela}_clube_id"
        if nome_indice not in {item["name"] for item in sa.inspect(bind).get_indexes(tabela)}:
            op.create_index(nome_indice, tabela, ["clube_id"])
        nome_fk = f"fk_{tabela}_clube"
        if nome_fk not in {item.get("name") for item in sa.inspect(bind).get_foreign_keys(tabela)}:
            op.create_foreign_key(nome_fk, tabela, "clubes", ["clube_id"], ["id"], ondelete="RESTRICT")
        op.alter_column(tabela, "clube_id", nullable=False)


def downgrade() -> None:
    raise RuntimeError("A reversão é bloqueada para preservar o isolamento dos dados.")

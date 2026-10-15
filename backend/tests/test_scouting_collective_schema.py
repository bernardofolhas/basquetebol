from sqlalchemy import create_engine, inspect, text

import database


def test_estrutura_coletiva_atualiza_instalacao_antiga(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as ligacao:
        ligacao.execute(text("CREATE TABLE scouting_blocos_coletivos (id INTEGER PRIMARY KEY, titulo VARCHAR(160))"))
        ligacao.execute(text("CREATE TABLE predefinicoes_relatorios (id INTEGER PRIMARY KEY)"))
        ligacao.execute(text("CREATE TABLE cadernos_playbook (id INTEGER PRIMARY KEY, equipa_id INTEGER)"))

    monkeypatch.setattr(database, "engine", engine)
    database.actualizar_estrutura_scouting_coletivo()
    database.actualizar_estrutura_scouting_coletivo()

    inspector = inspect(engine)
    assert "avaliacao" in {coluna["name"] for coluna in inspector.get_columns("scouting_blocos_coletivos")}
    assert "configuracao" in {coluna["name"] for coluna in inspector.get_columns("predefinicoes_relatorios")}
    assert "scouting_adversario_id" in {coluna["name"] for coluna in inspector.get_columns("cadernos_playbook")}
    assert "uq_caderno_scouting_equipa_adversario" in {indice["name"] for indice in inspector.get_indexes("cadernos_playbook")}

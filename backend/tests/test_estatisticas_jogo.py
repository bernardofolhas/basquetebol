from datetime import date
from pathlib import Path

from database import SessionLocal
from models.equipa import Equipa, EscalaoEnum, GeneroEnum
from models.estatistica import EventoEstatistica
from models.jogador import Jogador
from models.jogo import Jogo
from models.utilizador import Utilizador


ROOT = Path(__file__).resolve().parents[2]


def _criar_contexto():
    db = SessionLocal()
    clube_id = db.query(Utilizador.clube_id).filter(Utilizador.username == "admin").scalar()
    equipa = Equipa(
        clube_id=clube_id,
        nome="Equipa Teste Estatísticas",
        escalao=EscalaoEnum.senior,
        genero=GeneroEnum.masculino,
    )
    jogador = Jogador(clube_id=clube_id, equipa=equipa, nome="Atleta Estatística", numero_camisola=7)
    jogo = Jogo(
        clube_id=clube_id,
        equipa=equipa,
        data=date(2042, 2, 8),
        hora="18:00",
        adversario="Adversário Estatística",
        em_casa=True,
    )
    db.add_all([equipa, jogador, jogo])
    db.commit()
    return db, equipa.id, jogador.id, jogo.id


def _limpar(db, equipa_id):
    jogos_ids = [item[0] for item in db.query(Jogo.id).filter(Jogo.equipa_id == equipa_id).all()]
    if jogos_ids:
        db.query(EventoEstatistica).filter(EventoEstatistica.jogo_id.in_(jogos_ids)).delete(synchronize_session=False)
        db.query(Jogo).filter(Jogo.id.in_(jogos_ids)).delete(synchronize_session=False)
    db.query(Jogador).filter(Jogador.equipa_id == equipa_id).delete(synchronize_session=False)
    equipa = db.query(Equipa).filter(Equipa.id == equipa_id).first()
    if equipa:
        db.delete(equipa)
        db.commit()
    db.close()


def test_mesa_estatistica_renderiza_registo_offline(client_admin):
    db, equipa_id, jogador_id, jogo_id = _criar_contexto()
    try:
        resposta = client_admin.get(f"/estatisticas/jogos/{jogo_id}?offline=1")
        assert resposta.status_code == 200
        assert "Mesa estatística" in resposta.text
        assert "Guardar e sincronizar" in resposta.text
        assert 'data-stat-action="assistencia"' in resposta.text
        assert 'data-boxscore-player="' + str(jogador_id) + '"' in resposta.text

        dashboard = client_admin.get(f"/estatisticas/equipas/{equipa_id}")
        assert dashboard.status_code == 200
        assert "Registo de jogo, box scores" in dashboard.text
        assert f"/estatisticas/jogos/{jogo_id}" in dashboard.text
    finally:
        _limpar(db, equipa_id)


def test_sincronizacao_e_idempotente_e_atualiza_marcador(client_admin):
    db, equipa_id, jogador_id, jogo_id = _criar_contexto()
    try:
        eventos = [
            {"client_uid": "stats-test-0001", "jogador_id": jogador_id, "lado": "equipa", "tipo": "dois_c", "periodo": 1, "segundos_restantes": 540},
            {"client_uid": "stats-test-0002", "jogador_id": jogador_id, "lado": "equipa", "tipo": "tres_c", "periodo": 1, "segundos_restantes": 510},
            {"client_uid": "stats-test-0003", "jogador_id": None, "lado": "adversario", "tipo": "dois_c", "periodo": 1, "segundos_restantes": 500},
        ]
        primeira = client_admin.post(f"/estatisticas/jogos/{jogo_id}/sincronizar", json={"eventos": eventos})
        assert primeira.status_code == 200
        assert primeira.json()["marcador"] == {"equipa": 5, "adversario": 2}

        repetida = client_admin.post(f"/estatisticas/jogos/{jogo_id}/sincronizar", json={"eventos": eventos})
        assert repetida.status_code == 200
        assert db.query(EventoEstatistica).filter(EventoEstatistica.jogo_id == jogo_id).count() == 3

        eventos[0]["anulado"] = True
        anulada = client_admin.post(f"/estatisticas/jogos/{jogo_id}/sincronizar", json={"eventos": eventos})
        assert anulada.status_code == 200
        assert anulada.json()["marcador"] == {"equipa": 3, "adversario": 2}
        db.expire_all()
        jogo = db.query(Jogo).filter(Jogo.id == jogo_id).one()
        assert (jogo.pontos_nos, jogo.pontos_adversario) == (3, 2)
    finally:
        _limpar(db, equipa_id)


def test_sincronizacao_rejeita_atleta_de_outra_equipa(client_admin):
    db, equipa_id, _, jogo_id = _criar_contexto()
    try:
        resposta = client_admin.post(f"/estatisticas/jogos/{jogo_id}/sincronizar", json={"eventos": [{
            "client_uid": "stats-test-invalid", "jogador_id": 99999999,
            "lado": "equipa", "tipo": "assistencia", "periodo": 1,
        }]})
        assert resposta.status_code == 400
        assert db.query(EventoEstatistica).filter(EventoEstatistica.jogo_id == jogo_id).count() == 0
    finally:
        _limpar(db, equipa_id)


def test_sincronizacao_rejeita_identificador_de_outro_jogo(client_admin):
    db, equipa_id, jogador_id, jogo_id = _criar_contexto()
    outro = Jogo(
        clube_id=db.query(Equipa.clube_id).filter(Equipa.id == equipa_id).scalar(),
        equipa_id=equipa_id,
        data=date(2042, 2, 9),
        hora="18:00",
        adversario="Outro adversário",
        em_casa=False,
    )
    db.add(outro)
    db.commit()
    try:
        evento = {"client_uid": "stats-shared-uid", "jogador_id": jogador_id, "lado": "equipa", "tipo": "assistencia", "periodo": 1}
        primeira = client_admin.post(f"/estatisticas/jogos/{jogo_id}/sincronizar", json={"eventos": [evento]})
        segunda = client_admin.post(f"/estatisticas/jogos/{outro.id}/sincronizar", json={"eventos": [evento]})
        assert primeira.status_code == 200
        assert segunda.status_code == 409
    finally:
        _limpar(db, equipa_id)


def test_recursos_offline_e_atalhos_estao_configurados():
    base = (ROOT / "frontend" / "templates" / "base.html").read_text(encoding="utf-8")
    worker = (ROOT / "frontend" / "static" / "js" / "service-worker.js").read_text(encoding="utf-8")
    script = (ROOT / "frontend" / "static" / "js" / "basket-stats.js").read_text(encoding="utf-8")

    assert 'rel="manifest"' in base
    assert 'navigator.serviceWorker.register("/service-worker.js")' in base
    assert '/estatisticas/jogos/' in worker
    assert 'CACHE_STATS_PAGE' in worker
    assert 'CACHE_STATS_PAGE' in script
    assert "localStorage.setItem(storageKey" in script
    assert 'q:"ll_f"' in script

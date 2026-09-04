import json
from datetime import date
from pathlib import Path

from database import SessionLocal
from models.equipa import Equipa, EscalaoEnum, GeneroEnum
from models.estatistica import EventoEstatistica, MapeamentoJogadorEstatistica
from models.jogador import Jogador
from models.jogo import Jogo
from models.utilizador import Utilizador
from services.fiba_stats_service import ErroImportacaoFiba, interpretar_fiba


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
    db.query(MapeamentoJogadorEstatistica).filter(
        MapeamentoJogadorEstatistica.equipa_id == equipa_id
    ).delete(synchronize_session=False)
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
        assert 'data-court-dialog' in resposta.text
        assert 'data-stat-court' in resposta.text
        assert 'data-stat-reset' in resposta.text
        assert "Recomeçar estatística" in resposta.text
        assert 'data-boxscore-player="' + str(jogador_id) + '"' in resposta.text

        dashboard = client_admin.get(f"/estatisticas/equipas/{equipa_id}")
        assert dashboard.status_code == 200
        assert "Registo de jogo, box scores" in dashboard.text
        assert "FIBA LiveStats" in dashboard.text
        assert "Página FPB" in dashboard.text
        assert "Disponível" in dashboard.text
        assert f"/estatisticas/jogos/{jogo_id}/importar" in dashboard.text
        assert f"/estatisticas/jogos/{jogo_id}" in dashboard.text
    finally:
        _limpar(db, equipa_id)


def test_sincronizacao_e_idempotente_e_atualiza_marcador(client_admin):
    db, equipa_id, jogador_id, jogo_id = _criar_contexto()
    try:
        eventos = [
            {"client_uid": "stats-test-0001", "jogador_id": jogador_id, "lado": "equipa", "tipo": "dois_c", "periodo": 1, "segundos_restantes": 540, "posicao_x": 22.5, "posicao_y": 47.2},
            {"client_uid": "stats-test-0002", "jogador_id": jogador_id, "lado": "equipa", "tipo": "tres_c", "periodo": 1, "segundos_restantes": 510, "posicao_x": 76.1, "posicao_y": 18.4},
            {"client_uid": "stats-test-0003", "jogador_id": None, "lado": "adversario", "tipo": "dois_c", "periodo": 1, "segundos_restantes": 500, "posicao_x": 83.0, "posicao_y": 53.0},
        ]
        primeira = client_admin.post(f"/estatisticas/jogos/{jogo_id}/sincronizar", json={"eventos": eventos})
        assert primeira.status_code == 200
        assert primeira.json()["marcador"] == {"equipa": 5, "adversario": 2}

        repetida = client_admin.post(f"/estatisticas/jogos/{jogo_id}/sincronizar", json={"eventos": eventos})
        assert repetida.status_code == 200
        assert db.query(EventoEstatistica).filter(EventoEstatistica.jogo_id == jogo_id).count() == 3
        db.expire_all()
        guardado = db.query(EventoEstatistica).filter(EventoEstatistica.client_uid == "stats-test-0001").one()
        assert (guardado.posicao_x, guardado.posicao_y) == (22.5, 47.2)

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


def test_sincronizacao_rejeita_posicao_incompleta(client_admin):
    db, equipa_id, jogador_id, jogo_id = _criar_contexto()
    try:
        resposta = client_admin.post(f"/estatisticas/jogos/{jogo_id}/sincronizar", json={"eventos": [{
            "client_uid": "stats-position-invalid", "jogador_id": jogador_id,
            "lado": "equipa", "tipo": "assistencia", "periodo": 1,
            "posicao_x": 50,
        }]})
        assert resposta.status_code == 400
        assert "posição" in resposta.json()["message"].lower()
    finally:
        _limpar(db, equipa_id)


def test_reiniciar_folha_elimina_acoes_e_repor_resultado(client_admin):
    db, equipa_id, jogador_id, jogo_id = _criar_contexto()
    try:
        criada = client_admin.post(f"/estatisticas/jogos/{jogo_id}/sincronizar", json={"eventos": [{
            "client_uid": "stats-reset-event", "jogador_id": jogador_id,
            "lado": "equipa", "tipo": "tres_c", "periodo": 1,
            "segundos_restantes": 420, "posicao_x": 18.5, "posicao_y": 30.0,
        }]})
        assert criada.status_code == 200
        assert criada.json()["marcador"] == {"equipa": 3, "adversario": 0}

        resposta = client_admin.post(f"/estatisticas/jogos/{jogo_id}/reiniciar")
        assert resposta.status_code == 200
        assert resposta.json()["eventos_eliminados"] == 1
        assert resposta.json()["marcador"] == {"equipa": 0, "adversario": 0}
        assert db.query(EventoEstatistica).filter(EventoEstatistica.jogo_id == jogo_id).count() == 0
        db.expire_all()
        jogo = db.query(Jogo).filter(Jogo.id == jogo_id).one()
        assert jogo.pontos_nos is None
        assert jogo.pontos_adversario is None
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
    assert 'actionsWithoutPosition = new Set(["falta", "falta_sofrida"])' in script
    assert "requestEvent(button.dataset.opponentAction" in script
    assert "posicao_x:position?.x??null" in script
    assert "/reiniciar" in script
    assert "localStorage.removeItem(storageKey)" in script


def _ficheiro_fiba_json(nome_atleta="Atleta Estatística"):
    return json.dumps({
        "type": "playbyplay",
        "teams": [
            {
                "teamNumber": 1,
                "teamName": "Equipa Teste Estatísticas",
                "players": [{"pno": 7, "firstName": nome_atleta.split()[0], "familyName": " ".join(nome_atleta.split()[1:]), "shirtNumber": "7"}],
            },
            {"teamNumber": 2, "teamName": "Adversário Estatística", "players": []},
        ],
        "actions": [
            {"type": "action", "messageId": 101, "teamNumber": 1, "pno": 7, "period": 1, "clock": "09:31:00", "actionType": "2pt", "subType": "layup", "success": 1, "x": 22.5, "y": 47.2},
            {"type": "action", "messageId": 102, "teamNumber": 2, "period": 1, "clock": "09:10:00", "actionType": "3pt", "success": 0, "x": 75, "y": 20},
            {"type": "action", "messageId": 103, "teamNumber": 1, "pno": 7, "period": 1, "clock": "08:55:00", "actionType": "assist"},
            {"type": "action", "messageId": 104, "teamNumber": 1, "period": 1, "clock": "08:50:00", "actionType": "substitution"},
        ],
    }).encode()


def test_normalizador_fiba_interpreta_json_e_xml():
    json_resultado = interpretar_fiba(_ficheiro_fiba_json(), "jogo.json", "application/json")
    assert [item["tipo"] for item in json_resultado["eventos"]] == ["dois_c", "tres_f", "assistencia"]
    assert json_resultado["eventos"][0]["segundos_restantes"] == 571
    assert json_resultado["eventos"][0]["posicao_x"] == 22.5
    assert json_resultado["eventos_ignorados"] == 1
    assert json_resultado["jogadores"][0]["nome"] == "Atleta Estatística"

    xml = b"""<?xml version='1.0'?><game><teams><team teamNumber='1' teamName='Casa'><players><player pno='7' name='Atleta Estatistica' shirtNumber='7'/></players></team><team teamNumber='2' teamName='Fora'/></teams><playbyplay><action messageId='1' teamNumber='1' pno='7' period='2' clock='05:30:00' actionType='freethrow' success='1'/><action messageId='2' teamNumber='2' period='2' actionType='rebound' subType='offensive'/></playbyplay></game>"""
    xml_resultado = interpretar_fiba(xml, "jogo.xml", "application/xml")
    assert [item["tipo"] for item in xml_resultado["eventos"]] == ["ll_c", "ressalto_ofensivo"]
    assert xml_resultado["eventos"][0]["segundos_restantes"] == 330


def test_normalizador_fiba_rejeita_xml_perigoso():
    xml = b"<!DOCTYPE game [<!ENTITY xxe SYSTEM 'file:///etc/passwd'>]><game><action actionType='2pt'>&xxe;</action></game>"
    try:
        interpretar_fiba(xml, "jogo.xml", "application/xml")
    except Exception as exc:
        assert isinstance(exc, (ErroImportacaoFiba, ValueError))
    else:
        raise AssertionError("XML com entidades externas devia ser rejeitado")


def test_importacao_fiba_previsualiza_associa_e_nao_duplica(client_admin):
    db, equipa_id, jogador_id, jogo_id = _criar_contexto()
    conteudo = _ficheiro_fiba_json()
    try:
        pagina = client_admin.get(f"/estatisticas/jogos/{jogo_id}/importar")
        assert pagina.status_code == 200
        assert "Importar estatística oficial" in pagina.text
        assert "Ficheiro FIBA LiveStats" in pagina.text

        preview = client_admin.post(
            f"/estatisticas/jogos/{jogo_id}/fiba/previsualizar-ficheiro",
            files={"ficheiro": ("jogo.json", conteudo, "application/json")},
        )
        assert preview.status_code == 200
        assert preview.json()["eventos_suportados"] == 3
        assert preview.json()["eventos_ignorados"] == 1
        assert preview.json()["jogadores"][0]["jogador_id_sugerido"] == jogador_id

        dados = {"equipa_ficheiro": "1", "mapeamentos": json.dumps({"7": jogador_id})}
        primeira = client_admin.post(
            f"/estatisticas/jogos/{jogo_id}/fiba/importar-ficheiro",
            data=dados,
            files={"ficheiro": ("jogo.json", conteudo, "application/json")},
        )
        assert primeira.status_code == 200
        assert primeira.json()["criadas"] == 3
        assert primeira.json()["marcador"] == {"equipa": 2, "adversario": 0}

        segunda = client_admin.post(
            f"/estatisticas/jogos/{jogo_id}/fiba/importar-ficheiro",
            data=dados,
            files={"ficheiro": ("jogo.json", conteudo, "application/json")},
        )
        assert segunda.status_code == 200
        assert segunda.json()["criadas"] == 0
        assert segunda.json()["atualizadas"] == 3
        assert db.query(EventoEstatistica).filter(EventoEstatistica.jogo_id == jogo_id).count() == 3
        db.expire_all()
        evento = db.query(EventoEstatistica).filter(EventoEstatistica.tipo == "dois_c").one()
        assert evento.origem == "fiba_ficheiro"
        assert evento.subtipo == "layup"
        assert evento.jogador_id == jogador_id
        assert db.query(MapeamentoJogadorEstatistica).filter(
            MapeamentoJogadorEstatistica.equipa_id == equipa_id
        ).count() == 1
    finally:
        _limpar(db, equipa_id)

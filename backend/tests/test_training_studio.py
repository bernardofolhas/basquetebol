import asyncio
import json
from types import SimpleNamespace

from starlette.requests import Request

from models.equipa import Equipa
from models.treino import PlanoTreino
from models.treino import ExercicioPlano
from routers import treino
from routers.treino import (
    _campos_exercicio,
    _definir_desenho_campo,
    _definir_metadado_cena,
    _definir_slots_ativos,
    _serializar_cena_exercicio,
)
from services.desenho_service import empacotar_desenho_editavel


IMAGE = "data:image/png;base64,aW1hZ2U="


def test_training_studio_preserves_legacy_drawing_and_scene_order():
    exercise = ExercicioPlano(campos_ativos="1,2", desenho_1=IMAGE, desenho_2=None)
    _definir_metadado_cena(exercise, "@notas", 1, "Abrir no lado forte")
    _definir_slots_ativos(exercise, [2, 1])

    scenes = [_serializar_cena_exercicio(exercise, number) for number in [2, 1]]
    assert [scene["ordem"] for scene in scenes] == [0, 1]
    assert scenes[1]["desenho"] == IMAGE
    assert scenes[1]["estado"]["campoTipo"] == "meio"
    assert scenes[1]["observacao"] == "Abrir no lado forte"


def test_training_studio_keeps_court_type_notes_and_vector_state():
    exercise = ExercicioPlano(campos_ativos="5", desenhos_campos="{}")
    state = {
        "largura": 697,
        "altura": 1222,
        "campoTipo": "completo",
        "objectos": [{"tipo": "jogador_ataque", "x": 100, "y": 200, "numero": 1}],
    }
    _definir_desenho_campo(exercise, 5, empacotar_desenho_editavel(IMAGE, state))
    _definir_metadado_cena(exercise, "@tipos", 5, "completo")
    _definir_metadado_cena(exercise, "@notas", 5, "Passar e cortar")

    scene = _serializar_cena_exercicio(exercise, 5)
    field = _campos_exercicio(exercise)[0]
    assert scene["estado"]["objectos"] == state["objectos"]
    assert field["tipo"] == "completo"
    assert field["observacao"] == "Passar e cortar"
    assert field["desenho"] == IMAGE


def test_training_studio_new_scene_type_is_not_tied_to_legacy_slot_parity():
    exercise = ExercicioPlano(campos_ativos="1,2", desenhos_campos="{}")
    _definir_metadado_cena(exercise, "@tipos", 3, "completo")
    _definir_slots_ativos(exercise, [1, 3, 2])

    fields = _campos_exercicio(exercise)
    assert [field["tipo"] for field in fields] == ["meio", "completo", "completo"]
    assert [field["label"] for field in fields] == ["Campo meio", "Campo completo", "Campo completo 2"]


def test_training_studio_renders_the_playbook_interface_with_exercise_scenes(monkeypatch):
    exercise = ExercicioPlano(id=42, nome="Saída de pressão", campos_ativos="1,2", desenho_1=IMAGE)
    exercise.plano = PlanoTreino(sessao_id=9)
    team = Equipa(id=7, nome="Equipa de teste")

    class Query:
        def __init__(self, result):
            self.result = result

        def filter(self, *_args):
            return self

        def first(self):
            return self.result

    db = SimpleNamespace(query=lambda model: Query(exercise if model is ExercicioPlano else team))
    monkeypatch.setattr(treino, "_obter_equipa_id_por_exercicio", lambda *_args: team.id)
    monkeypatch.setattr(treino, "_verificar_acesso_treino", lambda *_args: None)
    request = Request({
        "type": "http", "method": "GET", "path": "/treino/exercicios/42/studio",
        "query_string": b"cena=2", "headers": [], "session": {}, "state": {"identidade_clube": {}},
    })

    response = treino.studio_exercicio(42, request, db, SimpleNamespace(nome="Treinador"))
    html = response.body.decode("utf-8")
    payload = json.loads(html.split('<script id="pbs-studio-data" type="application/json">', 1)[1].split("</script>", 1)[0])
    assert response.status_code == 200
    assert 'data-training-exercise="true"' in html
    assert 'data-initial-scene="2"' in html
    assert '/treino/sessoes/9/pdf' in html
    assert [scene["id"] for scene in payload["passos"]] == [1, 2]


def test_training_studio_scene_lifecycle_keeps_exercise_data(monkeypatch):
    exercise = ExercicioPlano(id=42, nome="Saída de pressão", campos_ativos="", desenhos_campos="{}")
    exercise.plano = PlanoTreino(sessao_id=9)

    class Query:
        def filter(self, *_args):
            return self

        def populate_existing(self):
            return self

        def with_for_update(self):
            return self

        def first(self):
            return exercise

    db = SimpleNamespace(query=lambda _model: Query(), commit=lambda: None)
    monkeypatch.setattr(treino, "_obter_equipa_id_por_exercicio", lambda *_args: 7)
    monkeypatch.setattr(treino, "_verificar_acesso_treino", lambda *_args: None)
    monkeypatch.setattr(treino, "_marcar_sessao_como_alterada_manual", lambda *_args: None)
    user = SimpleNamespace(nome="Treinador")

    def request(payload):
        body = json.dumps(payload).encode("utf-8")

        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        return Request({"type": "http", "method": "POST", "path": "/", "headers": [(b"accept", b"application/json")]}, receive)

    created = asyncio.run(treino.adicionar_cena_exercicio(42, request({"tipo": "completo"}), db, user))
    assert json.loads(created.body)["passo"]["estado"]["campoTipo"] == "completo"
    saved = asyncio.run(treino.guardar_desenho(42, request({
        "numero": 1, "dados": IMAGE,
        "estado": {"campoTipo": "completo", "largura": 697, "altura": 1222, "objectos": []},
    }), db, user))
    assert json.loads(saved.body)["sucesso"] is True
    asyncio.run(treino.guardar_observacao_cena_exercicio(42, 1, request({"observacao": "Passe de saída"}), db, user))

    duplicated = treino.duplicar_cena_exercicio(42, 1, db, user)
    assert json.loads(duplicated.body)["passo"]["observacao"] == "Passe de saída"
    assert _campos_exercicio(exercise)[1]["tipo"] == "completo"
    reordered = asyncio.run(treino.reordenar_cenas_exercicio(42, request({"passo_ids": [2, 1]}), db, user))
    assert json.loads(reordered.body)["passo_ids"] == [2, 1]
    deleted = asyncio.run(treino.apagar_campo_exercicio(42, 1, request({}), db, user))
    assert json.loads(deleted.body)["sucesso"] is True
    assert [field["numero"] for field in _campos_exercicio(exercise)] == [2]
    assert _campos_exercicio(exercise)[0]["observacao"] == "Passe de saída"

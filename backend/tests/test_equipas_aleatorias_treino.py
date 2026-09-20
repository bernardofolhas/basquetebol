import json
import random
from types import SimpleNamespace

from models.planeamento import Macrociclo, Mesociclo, Microciclo, SessaoTreino
from models.treino import PlanoTreino
from models.assiduidade import ConvocacaoAssiduidade
from models.equipa import Equipa, EscalaoEnum
from models.jogador import Jogador
from services.equipas_treino_service import gerar_equipas_equilibradas
from test_fase2_assiduidade_evolucao import _criar_contexto, _limpar_contexto
from routers.treino import _estado_equipas_guardado


def _jogadores(total: int) -> list[dict]:
    return [
        {
            "id": indice + 1,
            "nome": f"Atleta {indice + 1}",
            "interior": indice == 0,
            "altura": 200 - indice,
        }
        for indice in range(total)
    ]


def test_distribuicao_absorve_excedentes_sem_criar_equipa_incompleta():
    equipas_de_tres = gerar_equipas_equilibradas(_jogadores(10), 3, gerador=random.Random(7))
    equipas_de_quatro = gerar_equipas_equilibradas(_jogadores(10), 4, 2, random.Random(7))
    equipas_de_cinco = gerar_equipas_equilibradas(_jogadores(10), 5, 2, random.Random(7))

    assert [len(equipa["slots"]) for equipa in equipas_de_tres["equipas"]] == [3, 3, 4]
    assert [len(equipa["slots"]) for equipa in equipas_de_quatro["equipas"]] == [5, 5]
    assert len(equipas_de_quatro["grandes_ids"]) == 4
    for equipa in equipas_de_quatro["equipas"]:
        assert len(set(equipa["slots"]) & set(equipas_de_quatro["grandes_ids"])) == 2
    assert len(equipas_de_cinco["grandes_ids"]) == 4
    for equipa in equipas_de_cinco["equipas"]:
        assert len(set(equipa["slots"]) & set(equipas_de_cinco["grandes_ids"])) == 2


def test_equipas_de_cinco_usam_posicao_principal_depois_secundaria_e_altura():
    jogadores = _jogadores(10)
    for indice, jogador in enumerate(jogadores):
        jogador["altura"] = 160 + indice * 4
        jogador["posicao"] = "Base" if indice < 4 else "Extremo" if indice < 6 else "Poste"
        jogador["posicao_secundaria"] = "Extremo" if 2 <= indice < 4 else None

    resultado = gerar_equipas_equilibradas(jogadores, 5, gerador=random.Random(7))
    assert resultado["postes_por_equipa"] == 2
    for equipa in resultado["equipas"]:
        papeis = [resultado["posicoes_ids"][str(id_)] for id_ in equipa["slots"]]
        assert papeis.count("Base") == 1
        assert papeis.count("Extremo") == 2
        assert papeis.count("Poste") == 2
        assert papeis == ["Base", "Extremo", "Extremo", "Poste", "Poste"]
    assert all(resultado["posicoes_ids"][str(id_)] == "Extremo" for id_ in (3, 4))

    sem_posicoes = [{**jogador, "posicao": None, "posicao_secundaria": None} for jogador in jogadores]
    por_altura = gerar_equipas_equilibradas(sem_posicoes, 5, gerador=random.Random(7))
    assert {int(id_) for id_, papel in por_altura["posicoes_ids"].items() if papel == "Base"} == {1, 2}
    assert {int(id_) for id_, papel in por_altura["posicoes_ids"].items() if papel == "Poste"} == {7, 8, 9, 10}
    assert not any({9, 10}.issubset(set(equipa["slots"])) for equipa in por_altura["equipas"])


def test_equipas_de_quatro_respeitam_a_escolha_de_postes():
    jogadores = _jogadores(8)
    for jogador in jogadores:
        jogador["posicao"] = None
    for postes, extremos in ((1, 2), (2, 1)):
        resultado = gerar_equipas_equilibradas(jogadores, 4, postes, random.Random(7))
        for equipa in resultado["equipas"]:
            papeis = [resultado["posicoes_ids"][str(id_)] for id_ in equipa["slots"]]
            assert papeis.count("Base") == 1
            assert papeis.count("Extremo") == extremos
            assert papeis.count("Poste") == postes


def test_sem_altura_nao_inventa_bases_e_sem_posicao_nao_inventa_papel():
    jogadores = _jogadores(10)
    for indice, jogador in enumerate(jogadores):
        jogador["altura"] = None
        jogador["posicao"] = "Extremo" if indice < 6 else "Poste"
    resultado = gerar_equipas_equilibradas(jogadores, 5, gerador=random.Random(7))
    assert [len(equipa["slots"]) for equipa in resultado["equipas"]] == [5, 5]
    assert set(resultado["posicoes_ids"].values()) == {"Extremo", "Poste"}
    assert all(
        resultado["posicoes_ids"][str(jogador["id"])] == jogador["posicao"]
        for jogador in jogadores
    )

    sem_perfil = [{**jogador, "posicao": None} for jogador in jogadores]
    sem_papel = gerar_equipas_equilibradas(sem_perfil, 5, gerador=random.Random(7))
    assert sem_papel["posicoes_ids"] == {}
    assert [len(equipa["slots"]) for equipa in sem_papel["equipas"]] == [5, 5]


def test_alturas_de_outros_atletas_nao_reclassificam_quem_nao_tem_altura():
    jogadores = _jogadores(10)
    jogadores[0].update(altura=None, posicao="Extremo")
    jogadores[1].update(altura=None, posicao="Poste")
    resultado = gerar_equipas_equilibradas(jogadores, 5, gerador=random.Random(7))
    assert resultado["posicoes_ids"]["1"] == "Extremo"
    assert resultado["posicoes_ids"]["2"] == "Poste"
    assert {int(id_) for id_, papel in resultado["posicoes_ids"].items() if papel == "Base"}.isdisjoint({1, 2})


def test_gualdimir_extremo_poste_nao_passa_a_base_por_ser_baixo():
    jogadores = _jogadores(10)
    for indice, jogador in enumerate(jogadores):
        jogador["altura"] = 170 + indice * 2
        jogador["posicao"] = "Extremo" if indice < 6 else "Poste"
    jogadores[0].update(nome="Gualdimir Té", altura=155, posicao_secundaria="Poste")

    resultado = gerar_equipas_equilibradas(jogadores, 5, gerador=random.Random(7))
    assert resultado["posicoes_ids"]["1"] in {"Extremo", "Poste"}
    assert "Base" not in resultado["posicoes_ids"].values()
    assert [len(equipa["slots"]) for equipa in resultado["equipas"]] == [5, 5]


def test_extremo_base_muda_de_papel_conforme_necessidade_do_agrupamento():
    jogadores = _jogadores(5)
    for indice, jogador in enumerate(jogadores):
        jogador.update(posicao="Extremo" if indice < 2 else "Poste", altura=175 + indice * 4)
    jogadores[0]["posicao_secundaria"] = "Base"

    sem_base_principal = gerar_equipas_equilibradas(jogadores[:3], 3, gerador=random.Random(7))
    assert sem_base_principal["posicoes_ids"]["1"] == "Base"
    assert [sem_base_principal["posicoes_ids"][str(id_)] for id_ in sem_base_principal["equipas"][0]["slots"]] == ["Base", "Extremo", "Poste"]

    com_base_principal = gerar_equipas_equilibradas(
        [{**jogadores[1], "posicao": "Base"}, jogadores[0], *jogadores[2:]],
        5, gerador=random.Random(7),
    )
    assert com_base_principal["posicoes_ids"]["1"] == "Extremo"
    assert com_base_principal["posicoes_ids"]["2"] == "Base"
    equipa_de_quatro = gerar_equipas_equilibradas(
        [{**jogadores[1], "posicao": "Base"}, jogadores[0], *jogadores[2:4]],
        4, postes_por_equipa=2, gerador=random.Random(7),
    )
    assert equipa_de_quatro["posicoes_ids"]["1"] == "Extremo"


def test_extremos_com_base_secundaria_cobrem_duas_equipas_de_tres():
    jogadores = _jogadores(6)
    for indice, jogador in enumerate(jogadores):
        jogador.update(posicao="Extremo" if indice < 4 else "Poste", altura=175 + indice * 4)
        jogador["posicao_secundaria"] = "Base" if indice < 2 else None

    resultado = gerar_equipas_equilibradas(jogadores, 3, gerador=random.Random(7))
    assert {int(id_) for id_, papel in resultado["posicoes_ids"].items() if papel == "Base"} == {1, 2}
    for equipa in resultado["equipas"]:
        papeis = [resultado["posicoes_ids"][str(id_)] for id_ in equipa["slots"]]
        assert papeis == ["Base", "Extremo", "Poste"]


def test_estado_antigo_e_convertido_no_primeiro_agrupamento():
    plano = SimpleNamespace(equipas_aleatorias=json.dumps({
        "tamanho": 2,
        "postes_por_equipa": 0,
        "grandes_ids": [],
        "equipas": [{"nome": "Equipa 1", "slots": [1, 2]}],
    }))

    estado = _estado_equipas_guardado(plano, [1, 2])

    assert estado["grupos"][0]["id"] == 1
    assert estado["grupos"][0]["tamanho"] == 2
    assert estado["grupos"][0]["equipas"][0]["slots"] == [1, 2]


def test_agrupamento_guardado_corrige_papeis_deduzidos_sem_altura():
    plano = SimpleNamespace(equipas_aleatorias=json.dumps({
        "tamanho": 2,
        "postes_por_equipa": 0,
        "grandes_ids": [1, 2],
        "posicoes_ids": {"1": "Base", "2": "Poste"},
        "equipas": [{"nome": "Equipa 1", "slots": [1, 2]}],
    }))
    atletas = [
        {"id": 1, "altura": None, "posicao": "Extremo", "posicao_secundaria": None},
        {"id": 2, "altura": None, "posicao": None, "posicao_secundaria": None},
    ]
    grupo = _estado_equipas_guardado(plano, [1, 2], atletas)["grupos"][0]
    assert grupo["equipas"][0]["slots"] == [1, 2]
    assert grupo["posicoes_ids"] == {"1": "Extremo"}
    assert grupo["grandes_ids"] == []


def test_agrupamento_guardado_corrige_base_invalido_com_altura_registada():
    plano = SimpleNamespace(equipas_aleatorias=json.dumps({
        "tamanho": 2,
        "postes_por_equipa": 0,
        "grandes_ids": [1],
        "posicoes_ids": {"1": "Base", "2": "Extremo"},
        "equipas": [{"nome": "Equipa 1", "slots": [1, 2]}],
    }))
    atletas = [
        {"id": 1, "altura": 190, "posicao": "Extremo", "posicao_secundaria": "Poste"},
        {"id": 2, "altura": 175, "posicao": "Base", "posicao_secundaria": None},
    ]
    grupo = _estado_equipas_guardado(plano, [1, 2], atletas)["grupos"][0]
    assert grupo["posicoes_ids"] == {"1": "Extremo", "2": "Base"}
    assert grupo["grandes_ids"] == []
    assert grupo["equipas"][0]["slots"] == [1, 2]


def test_ordem_guardada_das_equipas_e_dos_atletas_nao_e_reorganizada():
    plano = SimpleNamespace(equipas_aleatorias=json.dumps({
        "grupos": [{
            "id": 4, "tamanho": 3, "postes_por_equipa": 1,
            "posicoes_ids": {"1": "Base", "2": "Extremo", "3": "Poste", "4": "Base"},
            "equipas": [
                {"nome": "Equipa 2", "slots": [4, 3]},
                {"nome": "Equipa 1", "slots": [2, 1]},
            ],
        }],
    }))
    grupo = _estado_equipas_guardado(plano, [1, 2, 3, 4])["grupos"][0]
    assert [equipa["slots"] for equipa in grupo["equipas"]] == [[4, 3], [2, 1]]
    assert [equipa["nome"] for equipa in grupo["equipas"]] == ["Equipa 1", "Equipa 2"]


def test_plano_convoca_escalhao_inferior_e_adiciona_aos_atletas_previstos_sem_refresh(client_admin):
    db, equipa_id, jogador_id, outro_id, macro_id = _criar_contexto()
    equipa_sub16 = None
    convocado = None
    try:
        equipa = db.query(Equipa).filter(Equipa.id == equipa_id).one()
        equipa_sub16 = Equipa(
            clube_id=equipa.clube_id,
            nome="Sub-16 de apoio",
            escalao=EscalaoEnum.sub16,
            genero=equipa.genero,
        )
        convocado = Jogador(
            clube_id=equipa.clube_id,
            nome="Atleta Sub-16 Convocado",
            numero_camisola=18,
            equipa=equipa_sub16,
        )
        db.add_all([equipa_sub16, convocado])
        db.commit()
        convocado_id = convocado.id
        sessao = db.query(SessaoTreino).join(Microciclo).join(Mesociclo).join(Macrociclo).filter(
            Macrociclo.id == macro_id
        ).one()

        pagina = client_admin.get(f"/treino/sessoes/{sessao.id}")
        assert pagina.status_code == 200
        assert "Convocar atletas Sub-16" in pagina.text
        assert "Atleta Sub-16 Convocado" in pagina.text
        plano = db.query(PlanoTreino).filter(PlanoTreino.sessao_id == sessao.id).one()

        resposta = client_admin.post(
            f"/treino/planos/{plano.id}/convocar-sub18",
            json={"jogador_ids": [convocado_id]},
        )
        assert resposta.status_code == 200
        assert resposta.json()["jogador_ids"][-1] == convocado_id
        assert resposta.json()["adicionados"][0]["nome"] == "Atleta Sub-16 Convocado"
        assert db.query(ConvocacaoAssiduidade).filter_by(
            sessao_id=sessao.id,
            jogador_id=convocado_id,
        ).count() == 1

        pagina_atualizada = client_admin.get(f"/treino/sessoes/{sessao.id}")
        assert "Convocado · Sub-16 de apoio" in pagina_atualizada.text
        assert f'data-sub18-option="{convocado_id}"' not in pagina_atualizada.text
    finally:
        if convocado is not None:
            db.query(ConvocacaoAssiduidade).filter(
                ConvocacaoAssiduidade.jogador_id == convocado.id,
            ).delete(synchronize_session=False)
            db.delete(convocado)
        if equipa_sub16 is not None:
            db.delete(equipa_sub16)
        db.commit()
        _limpar_contexto(db, equipa_id, jogador_id, outro_id, macro_id)
        db.close()


def test_plano_guarda_previstos_gera_e_reorganiza_equipas_sem_refresh(client_admin):
    db, equipa_id, jogador_id, outro_id, macro_id = _criar_contexto()
    try:
        sessao = db.query(SessaoTreino).join(Microciclo).join(Mesociclo).join(Macrociclo).filter(
            Macrociclo.id == macro_id
        ).one()
        pagina = client_admin.get(f"/treino/sessoes/{sessao.id}")
        assert pagina.status_code == 200
        assert "Atletas previstos" in pagina.text
        assert "Formar equipas" in pagina.text
        assert 'data-workspace-tab="atletas"' in pagina.text
        assert 'data-workspace-tab="equipas"' in pagina.text
        assert 'data-workspace-panel="treino:atletas"' in pagina.text
        assert 'data-workspace-panel="treino:equipas"' in pagina.text
        plano = db.query(PlanoTreino).filter(PlanoTreino.sessao_id == sessao.id).one()

        jogador = db.query(Jogador).filter(Jogador.id == jogador_id).one()
        editar = client_admin.post(
            f"/jogadores/{jogador_id}/editar",
            data={
                "nome": jogador.nome,
                "equipa_id": str(equipa_id),
                "posicao": "Poste",
                "posicao_secundaria": "Base",
            },
            follow_redirects=False,
        )
        assert editar.status_code == 303
        db.refresh(jogador)
        assert jogador.posicao_secundaria == "Base"
        perfil = client_admin.get(f"/jogadores/{jogador_id}/editar")
        assert 'name="posicao_secundaria"' in perfil.text
        assert 'value="Base" selected' in perfil.text

        previstos = client_admin.post(
            f"/treino/planos/{plano.id}/atletas-previstos",
            json={"jogador_ids": [jogador_id, outro_id]},
        )
        assert previstos.status_code == 200
        assert previstos.json()["jogador_ids"] == [jogador_id, outro_id]

        gerar = client_admin.post(
            f"/treino/planos/{plano.id}/equipas-aleatorias/gerar",
            json={"tamanho": 2, "postes_por_equipa": 1},
        )
        assert gerar.status_code == 200
        estado = gerar.json()["estado"]
        assert len(estado["grupos"]) == 1
        primeiro_grupo = estado["grupos"][0]
        assert primeiro_grupo["tamanho"] == 2
        assert set(primeiro_grupo["equipas"][0]["slots"]) == {jogador_id, outro_id}
        assert primeiro_grupo["posicoes_ids"][str(jogador_id)] == "Base"

        segundo = client_admin.post(
            f"/treino/planos/{plano.id}/equipas-aleatorias/gerar",
            json={"tamanho": 3, "postes_por_equipa": 1},
        )
        assert segundo.status_code == 200
        estado = segundo.json()["estado"]
        assert [grupo["tamanho"] for grupo in estado["grupos"]] == [2, 3]
        assert all(
            set(valor for equipa in grupo["equipas"] for valor in equipa["slots"] if valor is not None)
            == {jogador_id, outro_id}
            for grupo in estado["grupos"]
        )

        reorganizar = client_admin.post(
            f"/treino/planos/{plano.id}/equipas-aleatorias",
            json={"grupo_id": primeiro_grupo["id"], "equipas": [[jogador_id, None, outro_id]]},
        )
        assert reorganizar.status_code == 200
        assert reorganizar.json()["estado"]["grupos"][0]["equipas"][0]["slots"] == [jogador_id, None, outro_id]
        db.expire_all()
        guardado = json.loads(db.query(PlanoTreino).filter(PlanoTreino.id == plano.id).one().equipas_aleatorias)
        assert guardado["grupos"][0]["equipas"][0]["slots"] == [jogador_id, None, outro_id]
        assert len(guardado["grupos"]) == 2

        impressao = client_admin.get(f"/treino/sessoes/{sessao.id}/print")
        assert impressao.status_code == 200
        assert "Equipas do treino" in impressao.text
        assert "Equipa 1" in impressao.text
        assert "Agrupamento 2" in impressao.text
        assert "Equipas de 3" in impressao.text
        assert 'class="training-team-role">Base</span>' in impressao.text
        assert "Lugar por preencher" not in impressao.text
        assert "Lugar vazio" not in impressao.text
        assert impressao.text.index("Equipas do treino") > impressao.text.index('class="content"')

        pdf = client_admin.get(f"/treino/sessoes/{sessao.id}/pdf")
        assert pdf.status_code == 200
        assert pdf.headers["content-type"].startswith("application/pdf")
        assert pdf.content.startswith(b"%PDF")

        eliminar = client_admin.post(
            f"/treino/planos/{plano.id}/equipas-aleatorias/{estado['grupos'][1]['id']}/eliminar"
        )
        assert eliminar.status_code == 200
        assert len(eliminar.json()["estado"]["grupos"]) == 1
    finally:
        _limpar_contexto(db, equipa_id, jogador_id, outro_id, macro_id)
        db.close()

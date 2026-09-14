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

    assert [len(equipa["slots"]) for equipa in equipas_de_tres["equipas"]] == [3, 3, 4]
    assert [len(equipa["slots"]) for equipa in equipas_de_quatro["equipas"]] == [5, 5]
    assert len(equipas_de_quatro["grandes_ids"]) == 4
    for equipa in equipas_de_quatro["equipas"]:
        assert len(set(equipa["slots"]) & set(equipas_de_quatro["grandes_ids"])) == 2


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


def test_plano_convoca_sub18_e_adiciona_aos_atletas_previstos_sem_refresh(client_admin):
    db, equipa_id, jogador_id, outro_id, macro_id = _criar_contexto()
    equipa_sub18 = None
    convocado = None
    try:
        equipa = db.query(Equipa).filter(Equipa.id == equipa_id).one()
        equipa_sub18 = Equipa(
            clube_id=equipa.clube_id,
            nome="Sub-18 de apoio",
            escalao=EscalaoEnum.sub18,
            genero=equipa.genero,
        )
        convocado = Jogador(
            clube_id=equipa.clube_id,
            nome="Atleta Sub-18 Convocado",
            numero_camisola=18,
            equipa=equipa_sub18,
        )
        db.add_all([equipa_sub18, convocado])
        db.commit()
        convocado_id = convocado.id
        sessao = db.query(SessaoTreino).join(Microciclo).join(Mesociclo).join(Macrociclo).filter(
            Macrociclo.id == macro_id
        ).one()

        pagina = client_admin.get(f"/treino/sessoes/{sessao.id}")
        assert pagina.status_code == 200
        assert "Convocar atletas Sub-18" in pagina.text
        assert "Atleta Sub-18 Convocado" in pagina.text
        plano = db.query(PlanoTreino).filter(PlanoTreino.sessao_id == sessao.id).one()

        resposta = client_admin.post(
            f"/treino/planos/{plano.id}/convocar-sub18",
            json={"jogador_ids": [convocado_id]},
        )
        assert resposta.status_code == 200
        assert resposta.json()["jogador_ids"][-1] == convocado_id
        assert resposta.json()["adicionados"][0]["nome"] == "Atleta Sub-18 Convocado"
        assert db.query(ConvocacaoAssiduidade).filter_by(
            sessao_id=sessao.id,
            jogador_id=convocado_id,
        ).count() == 1

        pagina_atualizada = client_admin.get(f"/treino/sessoes/{sessao.id}")
        assert "Convocado · Sub-18 de apoio" in pagina_atualizada.text
        assert f'data-sub18-option="{convocado_id}"' not in pagina_atualizada.text
    finally:
        if convocado is not None:
            db.query(ConvocacaoAssiduidade).filter(
                ConvocacaoAssiduidade.jogador_id == convocado.id,
            ).delete(synchronize_session=False)
            db.delete(convocado)
        if equipa_sub18 is not None:
            db.delete(equipa_sub18)
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
        assert "Lugar por preencher" in impressao.text
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

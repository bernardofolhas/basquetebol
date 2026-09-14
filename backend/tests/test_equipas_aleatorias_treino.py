import json
import random

from models.planeamento import Macrociclo, Mesociclo, Microciclo, SessaoTreino
from models.treino import PlanoTreino
from services.equipas_treino_service import gerar_equipas_equilibradas
from test_fase2_assiduidade_evolucao import _criar_contexto, _limpar_contexto


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
        assert 'id="training-expected-dialog"' in pagina.text
        assert 'id="training-teams-dialog"' in pagina.text
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
        assert len(estado["equipas"]) == 1
        assert set(estado["equipas"][0]["slots"]) == {jogador_id, outro_id}

        reorganizar = client_admin.post(
            f"/treino/planos/{plano.id}/equipas-aleatorias",
            json={"equipas": [[jogador_id, None, outro_id]]},
        )
        assert reorganizar.status_code == 200
        assert reorganizar.json()["estado"]["equipas"][0]["slots"] == [jogador_id, None, outro_id]
        db.expire_all()
        guardado = json.loads(db.query(PlanoTreino).filter(PlanoTreino.id == plano.id).one().equipas_aleatorias)
        assert guardado["equipas"][0]["slots"] == [jogador_id, None, outro_id]

        impressao = client_admin.get(f"/treino/sessoes/{sessao.id}/print")
        assert impressao.status_code == 200
        assert "Equipas do treino" in impressao.text
        assert "Equipa 1" in impressao.text
        assert "Lugar por preencher" in impressao.text
        assert impressao.text.index("Equipas do treino") > impressao.text.index('class="content"')

        pdf = client_admin.get(f"/treino/sessoes/{sessao.id}/pdf")
        assert pdf.status_code == 200
        assert pdf.headers["content-type"].startswith("application/pdf")
        assert pdf.content.startswith(b"%PDF")
    finally:
        _limpar_contexto(db, equipa_id, jogador_id, outro_id, macro_id)
        db.close()

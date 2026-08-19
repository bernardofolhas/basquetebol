from services.planeamento_integrado_service import apresentar_treinos_por_perfil


def _itens_treino():
    return [{
        "categoria": "treino",
        "titulo": "Treino previsto pelo clube",
        "equipa_nome": "Sub-18 Femininos",
        "equipa_escalao": "Sub-18",
    }]


def test_treinador_ve_apenas_treino():
    itens = apresentar_treinos_por_perfil(_itens_treino(), "treinador")

    assert itens[0]["titulo"] == "Treino"


def test_coordenacao_identifica_equipa_e_escalao():
    itens = apresentar_treinos_por_perfil(_itens_treino(), "coordenador")

    assert itens[0]["titulo"] == "Treino de Sub-18 Femininos (Sub-18)"

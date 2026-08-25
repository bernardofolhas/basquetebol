from models.equipa import Equipa, EscalaoEnum, GeneroEnum
from services.linguagem_service import termo_jogador
from services.pdf_partilhavel_service import _sanitizar_item


def test_termo_do_atleta_respeita_genero_da_equipa():
    equipa_masculina = Equipa(nome="Masculinos", escalao=EscalaoEnum.senior, genero=GeneroEnum.masculino)
    equipa_feminina = Equipa(nome="Femininos", escalao=EscalaoEnum.senior, genero=GeneroEnum.feminino)

    assert termo_jogador(equipa_masculina) == "Jogador"
    assert termo_jogador(equipa_masculina, plural=True, capitalizar=False) == "jogadores"
    assert termo_jogador(equipa_feminina) == "Jogadora"
    assert termo_jogador(equipa_feminina, plural=True, capitalizar=False) == "jogadoras"
    assert termo_jogador(None, plural=True) == "Atletas"


def test_pdf_partilhavel_esconde_numeracao_interna_do_treino():
    item = _sanitizar_item({
        "id": "sessao-1",
        "data": None,
        "hora_inicio": "18:00",
        "hora_fim": "19:30",
        "horario": "18:00 - 19:30",
        "titulo": "Treino 7",
        "badge": "Treino",
        "categoria": "treino",
        "local": "Pavilhão",
        "equipa_nome": "Seniores",
    }, {})

    assert item["titulo"] == "Treino"

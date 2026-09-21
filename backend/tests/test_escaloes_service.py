from types import SimpleNamespace

from models.equipa import EscalaoEnum
from services.escaloes_service import escalao_imediatamente_inferior_da_equipa


def test_equipa_sub23_antiga_convoca_sub18_pelo_nome():
    equipa = SimpleNamespace(nome="Sub-23 Masculinos", escalao=EscalaoEnum.senior)

    assert escalao_imediatamente_inferior_da_equipa(equipa) == EscalaoEnum.sub18


def test_equipa_com_escalao_coerente_mantem_hierarquia():
    equipa = SimpleNamespace(nome="Equipa feminina", escalao=EscalaoEnum.sub18)

    assert escalao_imediatamente_inferior_da_equipa(equipa) == EscalaoEnum.sub16

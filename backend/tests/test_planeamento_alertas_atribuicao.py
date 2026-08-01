from datetime import date
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from main import app
from testsupport import TestClient


UTILIZADORES_TESTE = {
    "admin": {"username": "admin", "password": "admin123"},
}

NOME_EQUIPA_TESTE = "Equipa Alertas Atribuicao Sprint 13"
NOME_ESPACO_ATRIBUIDO = "Pavilhao Atribuido Sprint 13"


def _criar_client():
    return TestClient(app)


def _fazer_login(client: TestClient, perfil: str):
    response = client.post(
        "/login-form",
        data=UTILIZADORES_TESTE[perfil],
        follow_redirects=False,
    )
    assert response.status_code in [302, 303]
    assert response.headers["location"] == "/dashboard"


def _limpar_dados_teste():
    from database import SessionLocal
    from models.atribuicao_espaco_semanal import AtribuicaoEspacoSemanal
    from models.equipa import Equipa
    from models.espaco_treino import EspacoTreino
    from models.planeamento import Macrociclo, Mesociclo, Microciclo, SessaoTreino
    from models.planeamento_clube import PlanoSemanalClube, PlaneamentoClubeAnual, PlaneamentoClubeMensal

    db = SessionLocal()
    try:
        for atribuicao in db.query(AtribuicaoEspacoSemanal).all():
            if atribuicao.equipa and atribuicao.equipa.nome == NOME_EQUIPA_TESTE:
                db.delete(atribuicao)

        for semanal in db.query(PlanoSemanalClube).filter(
            PlanoSemanalClube.titulo == "Semanal Alertas Atribuicao Sprint 13"
        ).all():
            db.delete(semanal)

        for mensal in db.query(PlaneamentoClubeMensal).filter(
            PlaneamentoClubeMensal.titulo == "Mensal Alertas Atribuicao Sprint 13"
        ).all():
            db.delete(mensal)

        for anual in db.query(PlaneamentoClubeAnual).filter(
            PlaneamentoClubeAnual.titulo == "Anual Alertas Atribuicao Sprint 13"
        ).all():
            db.delete(anual)

        for sessao in db.query(SessaoTreino).all():
            if (
                sessao.microciclo
                and sessao.microciclo.mesociclo
                and sessao.microciclo.mesociclo.macrociclo
                and sessao.microciclo.mesociclo.macrociclo.equipa
                and sessao.microciclo.mesociclo.macrociclo.equipa.nome == NOME_EQUIPA_TESTE
            ):
                db.delete(sessao)

        for microciclo in db.query(Microciclo).all():
            if microciclo.mesociclo and microciclo.mesociclo.macrociclo and microciclo.mesociclo.macrociclo.equipa and microciclo.mesociclo.macrociclo.equipa.nome == NOME_EQUIPA_TESTE:
                db.delete(microciclo)

        for mesociclo in db.query(Mesociclo).all():
            if mesociclo.macrociclo and mesociclo.macrociclo.equipa and mesociclo.macrociclo.equipa.nome == NOME_EQUIPA_TESTE:
                db.delete(mesociclo)

        for macrociclo in db.query(Macrociclo).all():
            if macrociclo.equipa and macrociclo.equipa.nome == NOME_EQUIPA_TESTE:
                db.delete(macrociclo)

        for espaco in db.query(EspacoTreino).filter(EspacoTreino.nome == NOME_ESPACO_ATRIBUIDO).all():
            db.delete(espaco)

        for equipa in db.query(Equipa).filter(Equipa.nome == NOME_EQUIPA_TESTE).all():
            db.delete(equipa)

        db.commit()
    finally:
        db.close()


def _criar_contexto_microciclo_com_atribuicao():
    from database import SessionLocal
    from models.atribuicao_espaco_semanal import (
        AtribuicaoEspacoSemanal,
        EstadoAtribuicaoEspacoEnum,
        OrigemAtribuicaoEspacoEnum,
        TipoOcupacaoEspacoEnum,
    )
    from models.equipa import Equipa, EscalaoEnum, GeneroEnum
    from models.espaco_treino import EspacoTreino, TipoEspacoTreinoEnum
    from models.planeamento import Macrociclo, Mesociclo, Microciclo
    from models.planeamento_clube import (
        PlanoSemanalClube,
        PlaneamentoClubeAnual,
        PlaneamentoClubeMensal,
    )

    db = SessionLocal()
    try:
        equipa = Equipa(
            nome=NOME_EQUIPA_TESTE,
            escalao=EscalaoEnum.sub16,
            genero=GeneroEnum.masculino,
            seccionista=None,
        )
        db.add(equipa)
        db.commit()
        db.refresh(equipa)

        macro = Macrociclo(
            numero=1,
            data_inicio=date.fromisoformat("2026-04-01"),
            data_fim=date.fromisoformat("2026-04-30"),
            equipa_id=equipa.id,
        )
        db.add(macro)
        db.commit()
        db.refresh(macro)

        meso = Mesociclo(
            numero=1,
            data_inicio=date.fromisoformat("2026-04-01"),
            data_fim=date.fromisoformat("2026-04-30"),
            macrociclo_id=macro.id,
        )
        db.add(meso)
        db.commit()
        db.refresh(meso)

        micro = Microciclo(
            numero=1,
            data_inicio=date.fromisoformat("2026-04-14"),
            data_fim=date.fromisoformat("2026-04-20"),
            tipo="competitivo",
            mesociclo_id=meso.id,
        )
        db.add(micro)
        db.commit()
        db.refresh(micro)

        anual = PlaneamentoClubeAnual(
            epoca="2025/2026",
            titulo="Anual Alertas Atribuicao Sprint 13",
            data_inicio=date.fromisoformat("2025-09-01"),
            data_fim=date.fromisoformat("2026-06-30"),
        )
        db.add(anual)
        db.commit()
        db.refresh(anual)

        mensal = PlaneamentoClubeMensal(
            planeamento_anual_id=anual.id,
            ano=2026,
            mes=4,
            titulo="Mensal Alertas Atribuicao Sprint 13",
            estado="ativo",
        )
        db.add(mensal)
        db.commit()
        db.refresh(mensal)

        semanal = PlanoSemanalClube(
            titulo="Semanal Alertas Atribuicao Sprint 13",
            data_inicio=date.fromisoformat("2026-04-14"),
            data_fim=date.fromisoformat("2026-04-20"),
            estado="publicado",
            planeamento_mensal_id=mensal.id,
        )
        db.add(semanal)
        db.commit()
        db.refresh(semanal)

        espaco = EspacoTreino(
            nome=NOME_ESPACO_ATRIBUIDO,
            tipo=TipoEspacoTreinoEnum.pavilhao,
            localizacao="Complexo Desportivo",
            ativo=True,
        )
        db.add(espaco)
        db.commit()
        db.refresh(espaco)

        atribuicao = AtribuicaoEspacoSemanal(
            plano_semanal_id=semanal.id,
            espaco_id=espaco.id,
            equipa_id=equipa.id,
            data=date.fromisoformat("2026-04-16"),
            hora_inicio="09:00",
            hora_fim="11:00",
            tipo_ocupacao=TipoOcupacaoEspacoEnum.treino_equipa,
            estado=EstadoAtribuicaoEspacoEnum.publicado,
            origem=OrigemAtribuicaoEspacoEnum.manual,
        )
        db.add(atribuicao)
        db.commit()

        return micro.id
    finally:
        db.close()


def test_criar_sessao_mostra_banner_quando_local_diverge_da_atribuicao():
    client = _criar_client()
    _limpar_dados_teste()

    try:
        microciclo_id = _criar_contexto_microciclo_com_atribuicao()
        _fazer_login(client, "admin")

        response = client.post(
            f"/planeamento/microciclos/{microciclo_id}/sessoes/nova",
            data={
                "data": "2026-04-16",
                "local": "Pavilhao Alternativo",
                "volume_minutos": "90",
                "intensidade_rpe": "7",
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert "fora do espaço atribuído pelo clube" in response.text
        assert "Pavilhao Atribuido Sprint 13" in response.text
        assert "09:00-11:00" in response.text
        assert "Pavilhao Alternativo" in response.text
    finally:
        _limpar_dados_teste()

from datetime import date

import pytest

from auth import encriptar_password
from database import SessionLocal
from models.planeamento_clube import (
    PlaneamentoClubeAnual,
    PlaneamentoClubeMensal,
    PlanoSemanalClube,
)
from models.utilizador import PerfilEnum, Utilizador
from routers.planeamento_clube import (
    _normalizar_horas_evento,
    _validar_intervalo_datas,
)


@pytest.fixture
def client_treinador_fase0(client):
    """Cria um treinador efémero para não depender da password local da base de testes."""
    db = SessionLocal()
    utilizador = Utilizador(
        nome="Treinador Fase 0",
        username="fase0_treinador",
        email="fase0_treinador@example.test",
        password_hash=encriptar_password("fase0-password"),
        perfil=PerfilEnum.treinador,
        ativo=True,
    )
    db.add(utilizador)
    db.commit()
    response = client.post(
        "/login-form",
        data={"username": "fase0_treinador", "password": "fase0-password"},
        follow_redirects=False,
    )
    assert response.status_code in (302, 303)
    try:
        yield client
    finally:
        db.delete(utilizador)
        db.commit()
        db.close()


@pytest.mark.parametrize(
    ("rota", "dados"),
    [
        (
            "/planeamento-clube/anual/novo",
            {
                "epoca": "2026/2027",
                "titulo": "Não deve criar anual",
                "data_inicio": "2026-09-01",
                "data_fim": "2027-06-30",
            },
        ),
        (
            "/planeamento-clube/espacos/novo",
            {"nome": "Não deve criar espaço", "tipo": "pavilhao"},
        ),
        (
            "/planeamento-clube/eventos/novo",
            {
                "tipo": "evento_clube",
                "titulo": "Não deve criar evento",
                "data_evento": "2026-09-01",
            },
        ),
    ],
)
def test_treinador_nao_pode_submeter_escritas_planeamento_clube(client_treinador_fase0, rota, dados):
    response = client_treinador_fase0.post(rota, data=dados, follow_redirects=False)

    assert response.status_code in (302, 303)
    assert response.headers["location"] == "/dashboard"


def test_planeamento_anual_rejeita_intervalo_invalido_sem_erro_500(client_coordenador):
    response = client_coordenador.post(
        "/planeamento-clube/anual/novo",
        data={
            "epoca": "2026/2027",
            "titulo": "Intervalo inválido",
            "data_inicio": "2027-06-30",
            "data_fim": "2026-09-01",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/planeamento-clube/anual/novo"


def test_atribuicao_com_data_invalida_devolve_formulario_em_vez_de_name_error(client_coordenador):
    db = SessionLocal()
    anual = PlaneamentoClubeAnual(
        epoca="2026/2027",
        titulo="Fase 0 anual",
        data_inicio=date(2026, 9, 1),
        data_fim=date(2027, 6, 30),
    )
    db.add(anual)
    db.flush()
    mensal = PlaneamentoClubeMensal(
        planeamento_anual_id=anual.id,
        ano=2026,
        mes=9,
        titulo="Fase 0 mensal",
    )
    db.add(mensal)
    db.flush()
    semanal = PlanoSemanalClube(
        planeamento_mensal_id=mensal.id,
        titulo="Fase 0 semanal",
        data_inicio=date(2026, 9, 1),
        data_fim=date(2026, 9, 7),
    )
    db.add(semanal)
    db.commit()
    semanal_id = semanal.id

    try:
        response = client_coordenador.post(
            f"/planeamento-clube/semanal/{semanal_id}/atribuicoes/nova",
            data={
                "espaco_id": "1",
                "data_atribuicao": "data-invalida",
                "hora_inicio": "18:00",
                "hora_fim": "19:30",
                "tipo_ocupacao": "treino",
            },
            follow_redirects=False,
        )

        assert response.status_code == 400
        assert "data da atribuição" in response.text
    finally:
        db.delete(semanal)
        db.delete(mensal)
        db.delete(anual)
        db.commit()
        db.close()


def test_validadores_centrais_rejeitam_horas_e_datas_incoerentes():
    with pytest.raises(ValueError, match="data de início"):
        _validar_intervalo_datas("2027-06-30", "2026-09-01", "planeamento anual")

    with pytest.raises(ValueError, match="anterior"):
        _normalizar_horas_evento("19:30", "18:00")


def test_edicao_de_plano_semanal_devolve_formulario(client_coordenador):
    db = SessionLocal()
    anual = PlaneamentoClubeAnual(
        epoca="2038/2039",
        titulo="Auditoria anual",
        data_inicio=date(2038, 9, 1),
        data_fim=date(2039, 6, 30),
    )
    db.add(anual)
    db.flush()
    mensal = PlaneamentoClubeMensal(
        planeamento_anual_id=anual.id,
        ano=2038,
        mes=9,
        titulo="Auditoria mensal",
    )
    db.add(mensal)
    db.flush()
    semanal = PlanoSemanalClube(
        planeamento_mensal_id=mensal.id,
        titulo="Auditoria semanal",
        data_inicio=date(2038, 9, 6),
        data_fim=date(2038, 9, 12),
    )
    db.add(semanal)
    db.commit()
    semanal_id = semanal.id

    try:
        response = client_coordenador.get(f"/planeamento-clube/semanal/{semanal_id}/editar")
        assert response.status_code == 200
        assert "Editar Plano Semanal" in response.text
    finally:
        db.delete(semanal)
        db.delete(mensal)
        db.delete(anual)
        db.commit()
        db.close()

from datetime import date

from database import SessionLocal
from models.planeamento_clube import EventoPlaneamentoClube, TipoEventoPlaneamentoClubeEnum
from services.agenda_service import (
    TIPOS_AGENDA,
    intervalo_sobreposto,
    metadados_tipo_agenda,
)


def test_todos_os_tipos_de_evento_tem_metadados_de_agenda():
    for tipo in TipoEventoPlaneamentoClubeEnum:
        dados = metadados_tipo_agenda(tipo)
        assert dados["label"]
        assert dados["categoria"]
        assert dados["cor"]
    assert "folga" in TIPOS_AGENDA
    assert "teste_fisico" in TIPOS_AGENDA


def test_conflito_de_agenda_considera_dia_inteiro_e_intervalos():
    dia = date(2026, 8, 3)
    assert intervalo_sobreposto(dia, "18:00", "19:30", dia, "19:00", "20:00")
    assert not intervalo_sobreposto(dia, "18:00", "19:00", dia, "19:00", "20:00")
    assert intervalo_sobreposto(dia, None, None, dia, "19:00", "20:00")
    assert not intervalo_sobreposto(dia, "18:00", "19:00", date(2026, 8, 4), "18:00", "19:00")


def test_admin_consegue_criar_atividade_comum_de_dia_inteiro(client_admin):
    resposta = client_admin.post(
        "/agenda/atividades",
        data={
            "tipo": "folga",
            "titulo": "Recuperação da equipa",
            "data_evento": "2026-08-03",
            "hora_inicio": "",
            "hora_fim": "",
            "descricao": "Dia sem atividade de campo",
            "espaco_id": "",
            "equipa_id": "",
            "macrociclo_id": "",
            "mesociclo_id": "",
            "microciclo_id": "",
            "aplica_a_todas_equipas": "true",
            "retorno": "/calendario",
        },
        follow_redirects=False,
    )
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/calendario"

    db = SessionLocal()
    try:
        evento = db.query(EventoPlaneamentoClube).filter(
            EventoPlaneamentoClube.titulo == "Recuperação da equipa",
        ).first()
        assert evento is not None
        assert evento.tipo.value == "folga"
        db.delete(evento)
        db.commit()
    finally:
        db.close()

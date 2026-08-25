from datetime import date
from pathlib import Path

from database import SessionLocal
from models.planeamento_clube import EventoPlaneamentoClube, TipoEventoPlaneamentoClubeEnum
from services.agenda_service import (
    TIPOS_AGENDA,
    intervalo_sobreposto,
    metadados_tipo_agenda,
)
from routers.agenda import _datas_recorrencia, _fim_recorrencia


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


def test_recorrencia_semanal_sem_data_final_usa_o_fim_do_mesociclo():
    inicio = date(2026, 9, 7)
    fim_mesociclo = date(2026, 10, 4)

    fim = _fim_recorrencia(None, "semanal", fim_mesociclo)

    assert _datas_recorrencia(inicio, fim, "semanal", 1) == [
        date(2026, 9, 7),
        date(2026, 9, 14),
        date(2026, 9, 21),
        date(2026, 9, 28),
    ]


def test_data_final_indicada_pelo_utilizador_tem_prioridade_na_recorrencia():
    assert _fim_recorrencia(date(2026, 9, 21), "semanal", date(2026, 10, 4)) == date(2026, 9, 21)


def test_atividade_unica_pode_ser_transformada_numa_serie_semanal():
    datas = _datas_recorrencia(
        date(2026, 9, 14),
        _fim_recorrencia(None, "semanal", date(2026, 9, 28)),
        "semanal",
        1,
    )

    assert datas == [date(2026, 9, 14), date(2026, 9, 21), date(2026, 9, 28)]


def test_mesociclo_envia_os_dados_da_serie_para_o_editor_de_agenda():
    raiz = Path(__file__).resolve().parents[2]
    modelo = (raiz / "frontend" / "templates" / "planeamento" / "mesociclos" / "detalhe.html").read_text(encoding="utf-8")
    script = (raiz / "frontend" / "static" / "js" / "agenda.js").read_text(encoding="utf-8")

    assert 'data-workspace-always-default="true"' in modelo
    assert "data-agenda-data-fim" in modelo
    assert "data-agenda-serie-id" in modelo
    assert "data-agenda-recorrencia" in modelo
    assert "campo('agenda-escopo').value = 'serie'" in script


def test_link_do_plano_de_treino_tem_prioridade_sobre_o_clique_no_dia_do_calendario():
    raiz = Path(__file__).resolve().parents[2]
    script = (raiz / "frontend" / "static" / "js" / "agenda.js").read_text(encoding="utf-8")

    assert "if (link && !link.dataset.agendaEventId) return;" in script


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

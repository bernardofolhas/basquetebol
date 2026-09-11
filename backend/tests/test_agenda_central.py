from datetime import date
from pathlib import Path

from database import SessionLocal
from models.equipa import Equipa
from models.planeamento import Macrociclo
from models.planeamento_clube import EventoPlaneamentoClube, TipoEventoPlaneamentoClubeEnum
from models.utilizador import Utilizador
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


def test_macrociclo_envia_os_dados_da_serie_para_o_editor_de_agenda():
    raiz = Path(__file__).resolve().parents[2]
    modelo = (raiz / "frontend" / "templates" / "planeamento" / "macrociclos" / "detalhe.html").read_text(encoding="utf-8")
    script = (raiz / "frontend" / "static" / "js" / "agenda.js").read_text(encoding="utf-8")

    assert "data-agenda-data-fim" in modelo
    assert "data-agenda-serie-id" in modelo
    assert "data-agenda-recorrencia" in modelo
    assert "data-agenda-recorrencia-intervalo" in modelo
    assert "elemento.dataset.agendaRecorrenciaIntervalo || '1'" in script


def test_macrociclo_cria_treinos_semanais_ate_a_data_final(client_admin):
    db = SessionLocal()
    macro = None
    try:
        administrador = db.query(Utilizador).execution_options(ignorar_clube=True).filter(
            Utilizador.username == "admin"
        ).first()
        equipa = db.query(Equipa).execution_options(ignorar_clube=True).filter(
            Equipa.clube_id == administrador.clube_id
        ).order_by(Equipa.id).first()
        assert equipa is not None
        macro = Macrociclo(
            clube_id=equipa.clube_id,
            equipa_id=equipa.id,
            numero=997,
            data_inicio=date(2097, 1, 1),
            data_fim=date(2097, 3, 31),
        )
        db.add(macro)
        db.commit()
        macro_id = macro.id

        resposta = client_admin.post(
            "/agenda/atividades",
            data={
                "tipo": "treino_equipa",
                "titulo": "Treino recorrente do macrociclo",
                "data_evento": "2097-01-01",
                "data_fim": "2097-01-22",
                "recorrencia": "semanal",
                "recorrencia_intervalo": "1",
                "equipa_id": str(equipa.id),
                "macrociclo_id": str(macro_id),
                "mesociclo_id": "",
                "microciclo_id": "",
                "retorno": f"/planeamento/macrociclos/{macro_id}",
            },
            headers={"X-Requested-With": "XMLHttpRequest"},
            follow_redirects=False,
        )

        assert resposta.status_code == 200
        assert resposta.json()["sucesso"] is True
        db.expire_all()
        eventos = db.query(EventoPlaneamentoClube).execution_options(ignorar_clube=True).filter(
            EventoPlaneamentoClube.macrociclo_id == macro_id,
            EventoPlaneamentoClube.titulo == "Treino recorrente do macrociclo",
        ).order_by(EventoPlaneamentoClube.data).all()
        assert [evento.data for evento in eventos] == [
            date(2097, 1, 1),
            date(2097, 1, 8),
            date(2097, 1, 15),
            date(2097, 1, 22),
        ]
        assert len({evento.serie_id for evento in eventos}) == 1
        assert eventos[0].serie_id
    finally:
        if macro is not None:
            for evento in db.query(EventoPlaneamentoClube).execution_options(ignorar_clube=True).filter(
                EventoPlaneamentoClube.macrociclo_id == macro.id
            ).all():
                db.delete(evento)
            db.delete(macro)
            db.commit()
        db.close()


def test_link_do_plano_de_treino_tem_prioridade_sobre_o_clique_no_dia_do_calendario():
    raiz = Path(__file__).resolve().parents[2]
    script = (raiz / "frontend" / "static" / "js" / "agenda.js").read_text(encoding="utf-8")

    assert "if (link && !link.dataset.agendaEventId) return;" in script


def test_agenda_guarda_no_proprio_ecra_sem_criar_navegacao_intermedia():
    raiz = Path(__file__).resolve().parents[2]
    script = (raiz / "frontend" / "static" / "js" / "agenda.js").read_text(encoding="utf-8")

    assert "async function submeterAgenda" in script
    assert "evento.preventDefault();" in script
    assert "window.location.reload();" in script
    assert "agenda:retorno" in script


def test_agenda_assincrona_devolve_erro_sem_redirecionar(client_admin):
    resposta = client_admin.post(
        "/agenda/atividades",
        data={
            "tipo": "treino_equipa",
            "data_evento": "data-invalida",
            "retorno": "/calendario",
        },
        headers={"X-Requested-With": "XMLHttpRequest"},
        follow_redirects=False,
    )

    assert resposta.status_code == 400
    assert resposta.json()["sucesso"] is False
    assert "data" in resposta.json()["erro"].lower()


def test_csrf_devolve_json_para_pedidos_assincronos(client_admin):
    resposta = client_admin.post(
        "/agenda/atividades",
        data={"tipo": "folga", "data_evento": "2026-09-14"},
        headers={
            "Accept": "application/json",
            "X-Requested-With": "XMLHttpRequest",
            "X-CSRF-Token": "token-expirado",
        },
        follow_redirects=False,
    )

    assert resposta.status_code == 403
    assert resposta.headers["content-type"].startswith("application/json")
    assert resposta.json()["codigo"] == "csrf_invalido"


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

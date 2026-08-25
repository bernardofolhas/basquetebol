from datetime import date

from database import SessionLocal
from models.equipa import Equipa, EscalaoEnum, GeneroEnum
from models.planeamento import Macrociclo, Mesociclo, Microciclo, SessaoTreino
from services.planeamento_integrado_service import _item_sessao
from services.sessao_workflow import (
    estado_sessao_visual,
    opcoes_transicao_sessao,
    transicao_sessao_valida,
)


def test_workflow_da_sessao_expoe_transicoes_e_estado_visual():
    assert transicao_sessao_valida("planeada", "confirmada")
    assert transicao_sessao_valida("executada", "registada")
    assert transicao_sessao_valida("registada", "revista")
    assert not transicao_sessao_valida("planeada", "revista")
    assert estado_sessao_visual("executada")["label"] == "Executada"
    assert {item["codigo"] for item in opcoes_transicao_sessao("planeada")} == {"confirmada", "cancelada"}


def test_item_integrado_de_sessao_mostra_estado_e_proxima_acao():
    equipa = Equipa(
        nome="Equipa Fase 1 Item",
        escalao=EscalaoEnum.senior,
        genero=GeneroEnum.masculino,
    )
    macro = Macrociclo(numero=1, data_inicio=date(2035, 1, 1), data_fim=date(2035, 12, 31), equipa=equipa)
    meso = Mesociclo(numero=1, data_inicio=date(2035, 1, 1), data_fim=date(2035, 3, 31), macrociclo=macro)
    micro = Microciclo(numero=1, data_inicio=date(2035, 1, 6), data_fim=date(2035, 1, 12), mesociclo=meso)
    sessao = SessaoTreino(
        id=12345,
        data=date(2035, 1, 8),
        hora_inicio="18:00",
        hora_fim="19:30",
        local="Pavilhão Fase 1",
        estado="executada",
        microciclo=micro,
    )

    item = _item_sessao(sessao)

    assert item["estado"] == "executada"
    assert item["estado_label"] == "Executada"
    assert item["acao_label"] == "Registar sessão"
    assert item["acao_link"] == f"/assiduidade/sessoes/{sessao.id}"
    assert item["plano_treino_link"] == f"/treino/sessoes/{sessao.id}"


def test_admin_avanca_e_bloqueia_saltos_no_estado_da_sessao(client_admin):
    db = SessionLocal()
    clube_id = db.query(Equipa.clube_id).filter(Equipa.clube_id.isnot(None)).scalar()
    if not clube_id:
        db.close()
        return
    equipa = Equipa(
        clube_id=clube_id,
        nome="Equipa Fase 1 Workflow",
        escalao=EscalaoEnum.senior,
        genero=GeneroEnum.masculino,
    )
    macro = Macrociclo(clube_id=clube_id, numero=1, data_inicio=date(2036, 1, 1), data_fim=date(2036, 12, 31), equipa=equipa)
    meso = Mesociclo(clube_id=clube_id, numero=1, data_inicio=date(2036, 1, 1), data_fim=date(2036, 3, 31), macrociclo=macro)
    micro = Microciclo(clube_id=clube_id, numero=1, data_inicio=date(2036, 1, 6), data_fim=date(2036, 1, 12), mesociclo=meso)
    sessao = SessaoTreino(clube_id=clube_id, data=date(2036, 1, 8), microciclo=micro, estado="planeada")
    db.add(sessao)
    db.commit()
    sessao_id = sessao.id

    try:
        response = client_admin.post(
            f"/treino/sessoes/{sessao_id}/estado",
            data={"estado": "confirmada"},
            follow_redirects=False,
        )
        assert response.status_code == 303

        db.refresh(sessao)
        assert sessao.estado == "confirmada"

        response = client_admin.post(
            f"/treino/sessoes/{sessao_id}/estado",
            data={"estado": "revista"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        db.refresh(sessao)
        assert sessao.estado == "confirmada"
    finally:
        db.delete(macro)
        db.delete(equipa)
        db.commit()
        db.close()


def test_calendario_unificado_responde_em_html_e_pdf(client_admin):
    html = client_admin.get("/calendario?inicio=2035-01-01&fim=2035-01-07")
    assert html.status_code == 200
    assert "Calendário Operacional" in html.text
    assert "Agenda única" in html.text
    assert "← Anterior" in html.text
    assert "Seguinte →" in html.text
    assert "Janeiro 2035" in html.text

    pdf = client_admin.get("/calendario/pdf?inicio=2035-01-01&fim=2035-01-07")
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")


def test_plantel_da_equipa_e_lista_operacional_responsiva(client_admin):
    db = SessionLocal()
    try:
        equipa = db.query(Equipa).first()
        if not equipa:
            return
        resposta = client_admin.get(f"/equipas/{equipa.id}/plantel")
        assert resposta.status_code == 200
        assert "Lista operacional da equipa" in resposta.text
        assert 'id="selecionar-plantel"' in resposta.text
        assert f'name="equipa_id" value="{equipa.id}"' in resposta.text
        assert "ds-roster-list" in resposta.text
    finally:
        db.close()

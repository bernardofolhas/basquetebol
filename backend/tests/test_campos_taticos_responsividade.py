from datetime import date
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from auth import encriptar_password
from database import SessionLocal
from models.equipa import Equipa
from models.planeamento import Macrociclo, Mesociclo, Microciclo, SessaoTreino
from models.planeamento_clube import (
    EventoPlaneamentoClube,
    OrigemEventoPlaneamentoClubeEnum,
    TipoEventoPlaneamentoClubeEnum,
)
from models.treinador import Treinador
from models.treino import ExercicioPlano
from models.utilizador import PerfilEnum, Utilizador
from routers.treino import (
    _campos_exercicio,
    _contexto_impressao_plano,
    _definir_desenho_campo,
    _definir_slots_ativos,
    _proximo_numero_campo,
    _slots_ativos,
)
from services.planeamento_integrado_service import _item_evento


ROOT = Path(__file__).resolve().parents[2]


def test_exercicio_pode_ficar_sem_campos_e_recuperar_um_campo():
    exercicio = ExercicioPlano(campos_ativos="", desenho_1="desenho-antigo")

    assert _slots_ativos(exercicio) == []
    assert _campos_exercicio(exercicio) == []

    _definir_slots_ativos(exercicio, [2])
    assert exercicio.campos_ativos == "2"
    assert _campos_exercicio(exercicio)[0]["tipo"] == "completo"


def test_proximo_campo_continua_depois_de_duas_utilizacoes_do_mesmo_tipo():
    assert _proximo_numero_campo("meio", [1, 2, 3, 4]) == 5
    assert _proximo_numero_campo("completo", [1, 2, 3, 4, 5, 6]) == 8


def test_desenho_de_um_campo_adicional_pode_ser_guardado_e_removido():
    exercicio = ExercicioPlano(campos_ativos="1,2,3,4,5")

    _definir_desenho_campo(exercicio, 5, "desenho-editavel-5")
    assert _campos_exercicio(exercicio)[-1]["desenho"] == "desenho-editavel-5"

    _definir_desenho_campo(exercicio, 5, None)
    assert _campos_exercicio(exercicio)[-1]["desenho"] is None


def test_campos_mantem_ordem_e_desenhos_independentes_sem_limite_de_dois_por_tipo():
    exercicio = ExercicioPlano(
        campos_ativos="1,2,3,4,5,6",
        desenho_1="meio-1",
        desenho_2="completo-1",
        desenho_3="meio-2",
        desenho_4="completo-2",
        desenhos_campos=json.dumps({"5": "meio-3", "6": "completo-3"}),
    )

    campos = _campos_exercicio(exercicio)
    assert [campo["numero"] for campo in campos] == [1, 2, 3, 4, 5, 6]
    assert [campo["desenho"] for campo in campos] == ["meio-1", "completo-1", "meio-2", "completo-2", "meio-3", "completo-3"]
    assert [campo["tipo"] for campo in campos] == ["meio", "completo", "meio", "completo", "meio", "completo"]
    assert all(campo["estado_desenho"] is None for campo in campos)


def test_contexto_pdf_prepara_todos_os_campos_ativos():
    exercicio = ExercicioPlano(
        bloco="A",
        ordem=1,
        minutos=10,
        campos_ativos="1,2,3,4,5,6",
    )
    plano = SimpleNamespace(exercicios=[exercicio], blocos=[])
    sessao = SimpleNamespace(intensidade_rpe=6)
    request = SimpleNamespace(state=SimpleNamespace(identidade_clube={}))

    contexto = _contexto_impressao_plano(
        request,
        sessao,
        SimpleNamespace(treinadores=[]),
        plano,
        SimpleNamespace(nome="Treinador de teste", treinador=None),
    )

    assert len(exercicio.campos_pdf) == 6
    assert all(campo["imagem_composta"].startswith("data:image/png;base64,") for campo in exercicio.campos_pdf)
    assert contexto["total_exercicios"] == 1
    assert contexto["nome_treinador"] == "Treinador de teste"


def test_templates_expoem_navegacao_e_acoes_responsivas_sem_textos_internos():
    navegacao = (ROOT / "frontend/templates/partials/navbar_global.html").read_text(encoding="utf-8")
    biblioteca = (ROOT / "frontend/templates/biblioteca/detalhe.html").read_text(encoding="utf-8")
    calendario = (ROOT / "frontend/templates/calendario_partilhavel_pdf.html").read_text(encoding="utf-8")
    plano_pdf = (ROOT / "frontend/templates/treino/plano_print.html").read_text(encoding="utf-8")
    playbook = (ROOT / "frontend/templates/playbook/detalhe.html").read_text(encoding="utf-8")
    playbook_pdf = (ROOT / "frontend/templates/playbook/pdf.html").read_text(encoding="utf-8")

    for nivel in ("Plano anual", "Macrociclos", "Mesociclos", "Microciclos", "Planos de treino"):
        assert nivel in navegacao
    assert "canvas_bib_completo" in biblioteca
    assert "'cone'" in biblioteca
    assert "Documento para partilha" not in calendario
    assert "Documento operacional preparado pelo clube para partilha" not in calendario
    assert "ex.campos_pdf" in plano_pdf
    assert "identidade.nome_oficial" in plano_pdf
    assert "{% if plano and plano.reflexao %}" in plano_pdf
    assert "height: 25mm" not in plano_pdf
    assert ".court img { display: block; width: 100%; height: auto;" in plano_pdf
    assert "Ficha de treino" not in plano_pdf
    assert "imagemBase" in playbook
    assert "est.posicaoCursor = pos" in playbook
    assert "est.imagemBase = null" in playbook
    assert "passo.imagem_composta_pdf" in playbook_pdf
    assert 'src="/static/campos/campo_meio.png"' not in playbook_pdf


def test_header_liga_todos_os_niveis_a_listas_independentes():
    navegacao = (ROOT / "frontend/templates/partials/navbar_global.html").read_text(encoding="utf-8")
    contexto_equipa = (ROOT / "frontend/templates/partials/equipa_contexto.html").read_text(encoding="utf-8")

    assert "'/planeamento/equipas/' ~ equipa_contexto_id ~ '/mesociclos'" in navegacao
    assert "'/planeamento/equipas/' ~ equipa_contexto_id ~ '/microciclos'" in navegacao
    assert "'/treino/equipas/' ~ equipa_contexto_id ~ '/planos'" in navegacao
    assert "'/calendario?equipa_id=' ~ equipa_contexto_id" in navegacao
    assert 'class="ds-menu ds-primary-menu ds-nav-order-planeamento"' in navegacao
    assert 'class="ds-team-switcher"' in navegacao
    assert 'class="ds-team-direct-nav"' in navegacao
    assert 'ds-menu ds-primary-menu ds-nav-order-equipa' in navegacao
    assert "'/equipas/' ~ equipa_contexto_id ~ '/equipa-tecnica'" in navegacao
    for area in ("Resumo", "Planeamento", "Ação", "Análise", "Equipa"):
        assert area in navegacao
    for destino in ("Plantel", "Competição", "Assiduidade", "Eventos", "Análise física e testes", "Playbook"):
        assert destino in navegacao
    assert 'class="ds-tabs"' not in contexto_equipa
    assert 'data-planning-menu' not in contexto_equipa
    for nivel in ("Plano anual", "Macrociclos", "Mesociclos", "Microciclos", "Planos de treino"):
        assert nivel in navegacao

    estilos = (ROOT / "frontend/static/css/design-system.css").read_text(encoding="utf-8")
    base = (ROOT / "frontend/templates/base.html").read_text(encoding="utf-8")
    assert ".ds-header-navigation.is-open" in estilos
    assert ".ds-primary-menu>.ds-dropdown" in estilos
    assert ".ds-primary-nav > .ds-team-direct-nav { display:contents; }" in estilos
    for classe, ordem in (
        ("resumo", 1),
        ("planeamento", 2),
        ("acao", 3),
        ("analise", 4),
        ("equipa", 5),
    ):
        assert f".ds-nav-order-{classe} {{ order:{ordem}; }}" in estilos
    assert 'menuDetails.addEventListener("mouseleave"' in base
    assert "document.body.appendChild(submenu)" not in base


def test_header_usa_cor_solida_do_clube_e_texto_alternativo():
    estilos = (ROOT / "frontend/static/css/design-system.css").read_text(encoding="utf-8")
    base = (ROOT / "frontend/templates/base.html").read_text(encoding="utf-8")

    regras_topbar = [bloco for bloco in estilos.split("}") if ".ds-topbar" in bloco]
    assert regras_topbar
    assert all("linear-gradient" not in bloco and "radial-gradient" not in bloco for bloco in regras_topbar)
    assert "background:var(--clube-primary)" in estilos
    assert "color:var(--clube-header-text)" in estilos
    assert "--clube-header-text:" in base


def test_area_da_equipa_usa_apenas_navegacao_superior():
    base = (ROOT / "frontend/templates/base.html").read_text(encoding="utf-8")

    assert 'partials/sidebar_contextual.html' not in base
    assert 'id="sidebar-principal"' not in base
    assert 'class="ds-context-bar mb-4"' not in base


def test_treino_da_agenda_aponta_para_resolucao_do_plano():
    evento = EventoPlaneamentoClube(
        id=91,
        clube_id=2,
        tipo=TipoEventoPlaneamentoClubeEnum.treino_equipa,
        titulo="Treino global",
        data=date(2026, 9, 1),
        aplica_a_todas_equipas=True,
        origem=OrigemEventoPlaneamentoClubeEnum.manual,
    )

    item = _item_evento(evento, equipa_id=730)

    assert item["link"] == "/agenda/atividades/91/plano?equipa_id=730"
    assert item["plano_treino_link"] == "/agenda/atividades/91/plano?equipa_id=730"
    assert item["agenda_editavel"] is True


def test_abrir_treino_global_cria_sessao_e_abre_plano(client):
    db = SessionLocal()
    treinador = utilizador = macrociclo = evento = None
    try:
        equipa = db.query(Equipa).first()
        if not equipa:
            pytest.skip("A base de testes não tem uma equipa disponível.")

        macrociclo = Macrociclo(
            clube_id=equipa.clube_id,
            numero=991,
            data_inicio=date(2098, 9, 1),
            data_fim=date(2098, 9, 30),
            equipa_id=equipa.id,
        )
        db.add(macrociclo)
        db.flush()
        mesociclo = Mesociclo(
            clube_id=equipa.clube_id,
            numero=991,
            data_inicio=date(2098, 9, 1),
            data_fim=date(2098, 9, 30),
            macrociclo_id=macrociclo.id,
        )
        db.add(mesociclo)
        db.flush()
        microciclo = Microciclo(
            clube_id=equipa.clube_id,
            numero=991,
            data_inicio=date(2098, 9, 7),
            data_fim=date(2098, 9, 13),
            mesociclo_id=mesociclo.id,
        )
        db.add(microciclo)
        evento = EventoPlaneamentoClube(
            clube_id=equipa.clube_id,
            tipo=TipoEventoPlaneamentoClubeEnum.treino_equipa,
            titulo="Treino para abrir",
            data=date(2098, 9, 8),
            equipa_id=equipa.id,
            aplica_a_todas_equipas=False,
            origem=OrigemEventoPlaneamentoClubeEnum.manual,
        )
        db.add(evento)
        treinador = Treinador(clube_id=equipa.clube_id, nome="Treinador abertura plano")
        treinador.equipas.append(equipa)
        db.add(treinador)
        db.flush()
        utilizador = Utilizador(
            nome="Treinador abertura plano",
            username="coach_open_plan_test",
            email="coach-open-plan-test@example.invalid",
            password_hash=encriptar_password("Teste123!"),
            perfil=PerfilEnum.treinador,
            clube_id=equipa.clube_id,
            treinador_id=treinador.id,
            ativo=True,
        )
        db.add(utilizador)
        db.commit()
        evento_id, equipa_id = evento.id, equipa.id

        login = client.post(
            "/login-form",
            data={"username": utilizador.username, "password": "Teste123!"},
            follow_redirects=False,
        )
        assert login.status_code in (302, 303)

        abertura = client.get(
            f"/agenda/atividades/{evento_id}/plano?equipa_id={equipa_id}",
            follow_redirects=False,
        )
        assert abertura.status_code == 303
        assert abertura.headers["location"].startswith("/treino/sessoes/")

        plano = client.get(abertura.headers["location"], follow_redirects=False)
        assert plano.status_code == 200
        assert "Plano de Treino" in plano.text

        segunda_abertura = client.get(
            f"/agenda/atividades/{evento_id}/plano?equipa_id={equipa_id}",
            follow_redirects=False,
        )
        assert segunda_abertura.headers["location"] == abertura.headers["location"]

        db.expire_all()
        sessoes = db.query(SessaoTreino).filter(
            SessaoTreino.evento_planeamento_clube_id == evento_id,
        ).all()
        assert len(sessoes) == 1
        sessao = sessoes[0]
        assert sessao.microciclo_id == microciclo.id
        assert sessao.plano_treino is not None
    finally:
        db.rollback()
        if macrociclo:
            db.delete(macrociclo)
            db.flush()
        if evento:
            evento_atual = db.query(EventoPlaneamentoClube).filter(EventoPlaneamentoClube.id == evento.id).first()
            if evento_atual:
                db.delete(evento_atual)
        if utilizador:
            utilizador_atual = db.query(Utilizador).filter(Utilizador.id == utilizador.id).first()
            if utilizador_atual:
                db.delete(utilizador_atual)
        if treinador:
            treinador_atual = db.query(Treinador).filter(Treinador.id == treinador.id).first()
            if treinador_atual:
                treinador_atual.equipas.clear()
                db.delete(treinador_atual)
        db.commit()
        db.close()


def test_treinador_abre_listas_de_planeamento_diretamente(client):
    db = SessionLocal()
    treinador = None
    utilizador = None
    try:
        equipa = db.query(Equipa).first()
        if not equipa:
            pytest.skip("A base de testes não tem uma equipa disponível.")
        treinador = Treinador(clube_id=equipa.clube_id, nome="Treinador navegação")
        treinador.equipas.append(equipa)
        db.add(treinador)
        db.flush()
        utilizador = Utilizador(
            nome="Treinador navegação",
            username="coach_navigation_test",
            email="coach-navigation-test@example.invalid",
            password_hash=encriptar_password("Teste123!"),
            perfil=PerfilEnum.treinador,
            clube_id=equipa.clube_id,
            treinador_id=treinador.id,
            ativo=True,
        )
        db.add(utilizador)
        db.commit()
        equipa_id = equipa.id

        login = client.post(
            "/login-form",
            data={"username": utilizador.username, "password": "Teste123!"},
            follow_redirects=False,
        )
        assert login.status_code in (302, 303)

        destinos = {
            f"/planeamento/equipas/{equipa_id}/anuais": "Planeamento anual da equipa",
            f"/planeamento/equipas/{equipa_id}/macrociclos": "Planeamento da Equipa",
            f"/planeamento/equipas/{equipa_id}/mesociclos": "Mesociclos",
            f"/planeamento/equipas/{equipa_id}/microciclos": "Microciclos",
            f"/treino/equipas/{equipa_id}/planos": "Planos de treino",
        }
        for destino, texto in destinos.items():
            resposta = client.get(destino, follow_redirects=False)
            assert resposta.status_code == 200, destino
            assert texto in resposta.text

        planos = client.get(f"/treino/equipas/{equipa_id}/planos")
        assert "Calendário Operacional" not in planos.text
    finally:
        if utilizador:
            db.delete(utilizador)
        if treinador:
            treinador.equipas.clear()
            db.delete(treinador)
        db.commit()
        db.close()

from pathlib import Path
from types import SimpleNamespace

import pytest

from auth import encriptar_password
from database import SessionLocal
from models.equipa import Equipa
from models.treinador import Treinador
from models.treino import ExercicioPlano
from models.utilizador import PerfilEnum, Utilizador
from routers.treino import _campos_exercicio, _contexto_impressao_plano, _definir_slots_ativos, _slots_ativos


ROOT = Path(__file__).resolve().parents[2]


def test_exercicio_pode_ficar_sem_campos_e_recuperar_um_campo():
    exercicio = ExercicioPlano(campos_ativos="", desenho_1="desenho-antigo")

    assert _slots_ativos(exercicio) == []
    assert _campos_exercicio(exercicio) == []

    _definir_slots_ativos(exercicio, [2])
    assert exercicio.campos_ativos == "2"
    assert _campos_exercicio(exercicio)[0]["tipo"] == "completo"


def test_campos_mantem_ordem_e_desenhos_independentes():
    exercicio = ExercicioPlano(
        campos_ativos="1,2,3,4",
        desenho_1="meio-1",
        desenho_2="completo-1",
        desenho_3="meio-2",
        desenho_4="completo-2",
    )

    campos = _campos_exercicio(exercicio)
    assert [campo["numero"] for campo in campos] == [1, 2, 3, 4]
    assert [campo["desenho"] for campo in campos] == ["meio-1", "completo-1", "meio-2", "completo-2"]


def test_contexto_pdf_prepara_todos_os_campos_ativos():
    exercicio = ExercicioPlano(
        bloco="A",
        ordem=1,
        minutos=10,
        campos_ativos="1,2,3,4",
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

    assert len(exercicio.campos_pdf) == 4
    assert all(campo["imagem_composta"].startswith("data:image/png;base64,") for campo in exercicio.campos_pdf)
    assert contexto["total_exercicios"] == 1
    assert contexto["nome_treinador"] == "Treinador de teste"


def test_templates_expoem_navegacao_e_acoes_responsivas_sem_textos_internos():
    sidebar = (ROOT / "frontend/templates/partials/sidebar_contextual.html").read_text(encoding="utf-8")
    biblioteca = (ROOT / "frontend/templates/biblioteca/detalhe.html").read_text(encoding="utf-8")
    calendario = (ROOT / "frontend/templates/calendario_partilhavel_pdf.html").read_text(encoding="utf-8")
    plano_pdf = (ROOT / "frontend/templates/treino/plano_print.html").read_text(encoding="utf-8")

    for nivel in ("Plano anual", "Macrociclos", "Mesociclos", "Microciclos", "Planos de treino"):
        assert nivel in sidebar
    assert "canvas_bib_completo" in biblioteca
    assert "'cone'" in biblioteca
    assert "Documento para partilha" not in calendario
    assert "Documento operacional preparado pelo clube para partilha" not in calendario
    assert "ex.campos_pdf" in plano_pdf
    assert "identidade.nome_oficial" in plano_pdf


def test_sidebar_liga_todos_os_niveis_a_listas_independentes():
    sidebar = (ROOT / "frontend/templates/partials/sidebar_contextual.html").read_text(encoding="utf-8")

    assert "'/planeamento/equipas/' ~ equipa_contexto_id ~ '/mesociclos'" in sidebar
    assert "'/planeamento/equipas/' ~ equipa_contexto_id ~ '/microciclos'" in sidebar
    assert "'/treino/equipas/' ~ equipa_contexto_id ~ '/planos'" in sidebar
    assert "('/calendario?equipa_id=' ~ equipa_contexto_id)" not in sidebar
    assert "is-disabled" not in sidebar


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

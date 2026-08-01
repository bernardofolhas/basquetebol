from pathlib import Path
from types import SimpleNamespace

from models.treino import ExercicioPlano
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

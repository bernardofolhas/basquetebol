from datetime import date
from io import BytesIO

from pypdf import PdfReader

from models.utilizador import PerfilEnum
from services.navegacao_service import _agrupar_pendencias, _acoes_rapidas
from services.identidade_clube_service import CORES_PADRAO, _enriquecer_identidade
from services.pdf_partilhavel_service import _sanitizar_item, preparar_calendario_intervalo_partilhavel


class _Utilizador:
    def __init__(self, perfil):
        self.perfil = perfil


def test_pendencias_sao_agrupadas_e_priorizadas():
    tarefas = [
        {"titulo": "Criar convocatória", "link": "/jogos/1", "urgente": False, "item": {"data": date(2026, 8, 2)}},
        {"titulo": "Resolver conflito de espaço", "link": "/dashboard/clube/espacos", "urgente": True, "item": {"data": date(2026, 8, 1)}},
    ]
    grupos = _agrupar_pendencias(tarefas)
    assert [grupo["chave"] for grupo in grupos] == ["jogos", "espacos"]
    assert grupos[1]["itens"][0]["prioridade"] == "alta"


def test_acoes_rapidas_respeitam_perfil():
    treinador = _acoes_rapidas(_Utilizador(PerfilEnum.treinador), [])
    coordenador = _acoes_rapidas(_Utilizador(PerfilEnum.coordenador), [])
    assert not any(acao["label"] == "Adicionar jogador" for acao in treinador)
    assert any(acao["label"] == "Adicionar jogador" for acao in coordenador)


def test_identidade_calcula_contraste_para_cores_claras():
    identidade = _enriquecer_identidade({
        **CORES_PADRAO,
        "cor_secundaria": "#ffffff",
        "cor_destaque": "#fff700",
    })
    assert identidade["texto_sobre_secundaria"] == "#111827"
    assert identidade["texto_sobre_destaque"] == "#111827"


def test_pdf_partilhavel_remove_reflexao_e_observacoes_internas():
    item = {
        "id": "sessao-44",
        "data": date(2026, 8, 1),
        "hora_inicio": "18:00",
        "hora_fim": "19:30",
        "horario": "18:00-19:30",
        "titulo": "Treino 12",
        "badge": "Treino",
        "categoria": "treino",
        "local": "Pavilhão",
        "equipa_nome": "Sub-18",
        "detalhe": "REFLEXAO_PRIVADA_NAO_PARTILHAR",
    }
    publico = _sanitizar_item(item, {})
    assert publico["descricao_publica"] is None
    assert "REFLEXAO_PRIVADA" not in str(publico)


def test_pdf_partilhavel_usa_apenas_descricao_publica_de_evento():
    item = {
        "id": "evento-9", "data": date(2026, 8, 1), "hora_inicio": None,
        "hora_fim": None, "horario": "Hora por definir", "titulo": "Apresentação",
        "badge": "Evento", "categoria": "atividade", "local": None,
        "equipa_nome": "Clube", "detalhe": "NOTA_INTERNA",
    }
    publico = _sanitizar_item(item, {"evento-9": "Entrada pela porta principal"})
    assert publico["descricao_publica"] == "Entrada pela porta principal"
    assert "NOTA_INTERNA" not in str(publico)


def test_barra_global_aparece_sem_rotulo_clube_atual(client_admin):
    response = client_admin.get("/dashboard")
    assert response.status_code == 200
    assert "Pesquisar no clube" in response.text
    assert "Pendências" in response.text
    assert "Clube atual:" not in response.text


def test_calendario_partilhavel_gera_pdf_a4(client_admin):
    response = client_admin.get("/partilha/calendario/pdf?inicio=2026-08-01&fim=2026-08-31")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
    texto = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(response.content)).pages)
    assert "Calendário operacional" in texto
    assert "Documento para partilha" not in texto
    assert "Documento operacional preparado pelo clube para partilha" not in texto


def test_calendario_pdf_completo_continua_disponivel(client_admin):
    response = client_admin.get("/calendario/pdf?inicio=2026-08-01&fim=2026-08-31")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")


def test_calendario_partilhavel_de_mesociclo_mantem_apenas_dias_do_intervalo(monkeypatch):
    import services.pdf_partilhavel_service as servico

    monkeypatch.setattr(servico, "preparar_agenda_partilhavel", lambda *args, **kwargs: {
        "itens": [{"data": date(2026, 1, 31), "titulo": "Treino"}],
    })
    agenda = preparar_calendario_intervalo_partilhavel(None, date(2026, 1, 31), date(2026, 2, 2), equipa_ids=[1])
    dias = [dia["data"] for semana in agenda["semanas_intervalo"] for dia in semana if dia]
    assert dias == [date(2026, 1, 31), date(2026, 2, 1), date(2026, 2, 2)]
    assert agenda["meses_intervalo"] == "Janeiro 2026 · Fevereiro 2026"

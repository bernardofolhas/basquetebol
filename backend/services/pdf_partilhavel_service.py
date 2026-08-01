"""Prepara agendas para partilha externa sem transportar dados internos."""

from collections import defaultdict
from datetime import date

from models.atividade import Atividade
from models.planeamento_clube import EventoPlaneamentoClube
from services.planeamento_integrado_service import obter_dashboard_planeamento_intervalo

DIAS_SEMANA = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira", "Sábado", "Domingo"]


def _descricao_publica_por_id(db, itens: list[dict]) -> dict[str, str]:
    evento_ids = [int(item["id"].split("-", 1)[1]) for item in itens if item["id"].startswith("evento-")]
    atividade_ids = [int(item["id"].split("-", 1)[1]) for item in itens if item["id"].startswith("atividade-")]
    publicas = {}
    if evento_ids:
        for evento in db.query(EventoPlaneamentoClube).filter(EventoPlaneamentoClube.id.in_(evento_ids)).all():
            # "descricao" é o campo público; "observacoes" é deliberadamente excluído.
            if evento.descricao:
                publicas[f"evento-{evento.id}"] = evento.descricao.strip()
    if atividade_ids:
        for atividade in db.query(Atividade).filter(Atividade.id.in_(atividade_ids)).all():
            if atividade.descricao:
                publicas[f"atividade-{atividade.id}"] = atividade.descricao.strip()
    return publicas


def _sanitizar_item(item: dict, descricoes_publicas: dict[str, str]) -> dict:
    descricao = descricoes_publicas.get(item["id"])
    if item["id"].startswith("jogo-"):
        descricao = item.get("detalhe")  # competição ou indicação casa/fora
    return {
        "id": item["id"],
        "data": item["data"],
        "hora_inicio": item.get("hora_inicio"),
        "hora_fim": item.get("hora_fim"),
        "horario": item.get("horario") or "Hora por definir",
        "titulo": item["titulo"],
        "tipo": item.get("badge") or item.get("categoria", "Evento").title(),
        "categoria": item.get("categoria", "outro"),
        "local": item.get("local") or "Local por definir",
        "equipa_nome": item.get("equipa_nome") or "Clube",
        "descricao_publica": descricao,
    }


def preparar_agenda_partilhavel(
    db,
    data_inicio: date,
    data_fim: date,
    *,
    equipa_ids: list[int] | None = None,
    categorias: set[str] | None = None,
) -> dict:
    """Constrói dados mínimos, deduplicados e prontos para impressão."""
    if equipa_ids:
        itens_por_id = {}
        for equipa_id in equipa_ids:
            dashboard = obter_dashboard_planeamento_intervalo(db, data_inicio, data_fim, equipa_id=equipa_id)
            for item in dashboard["itens"]:
                itens_por_id[item["id"]] = item
        itens = list(itens_por_id.values())
    else:
        itens = obter_dashboard_planeamento_intervalo(db, data_inicio, data_fim)["itens"]
    if categorias:
        itens = [item for item in itens if item.get("categoria") in categorias]

    descricoes = _descricao_publica_por_id(db, itens)
    itens_publicos = [_sanitizar_item(item, descricoes) for item in itens]
    itens_publicos.sort(key=lambda item: (item["data"], item["hora_inicio"] or "99:99", item["titulo"].lower()))

    por_data = defaultdict(list)
    for item in itens_publicos:
        por_data[item["data"]].append(item)
    dias = [{"data": data_item, "dia_semana": DIAS_SEMANA[data_item.weekday()], "itens": itens_dia} for data_item, itens_dia in sorted(por_data.items())]
    return {
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        "itens": itens_publicos,
        "dias": dias,
        "totais": {
            "eventos": len(itens_publicos),
            "treinos": sum(1 for item in itens_publicos if item["categoria"] == "treino"),
            "jogos": sum(1 for item in itens_publicos if item["categoria"] == "jogo"),
            "atividades": sum(1 for item in itens_publicos if item["categoria"] not in {"treino", "jogo"}),
        },
    }

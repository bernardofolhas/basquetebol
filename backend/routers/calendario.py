import calendar
from calendar import monthrange
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response
from template_config import Jinja2Templates
from sqlalchemy.orm import Session

from auth_deps import exigir_autenticacao
from database import get_db
from models.equipa import Equipa
from models.espaco_treino import EspacoTreino
from models.treinador import Treinador
from paths import TEMPLATES_DIR
from services.agenda_service import tipos_agenda_formulario
from services.planeamento_integrado_service import obter_dashboard_planeamento_intervalo
from services.pdf_service import renderizar_pdf

router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _converter_data_query(valor: str | None, fallback: date) -> date:
    try:
        return date.fromisoformat((valor or "").strip())
    except (TypeError, ValueError):
        return fallback


def _periodo_calendario(request: Request) -> tuple[date, date]:
    hoje = date.today()
    inicio_padrao = date(hoje.year, hoje.month, 1)
    fim_padrao = date(hoje.year, hoje.month, monthrange(hoje.year, hoje.month)[1])
    inicio = _converter_data_query(request.query_params.get("inicio"), inicio_padrao)
    fim = _converter_data_query(request.query_params.get("fim"), fim_padrao)
    if inicio > fim:
        inicio, fim = fim, inicio
    return inicio, fim


def _equipas_visiveis(db: Session, utilizador) -> list[Equipa]:
    if utilizador.perfil.value == "treinador":
        treinador = db.query(Treinador).filter(Treinador.id == utilizador.treinador_id).first()
        return list(treinador.equipas) if treinador else []
    return db.query(Equipa).order_by(Equipa.nome).all()


def _obter_itens_calendario(db: Session, inicio: date, fim: date, equipa_ids: list[int] | None):
    if equipa_ids is None:
        return obter_dashboard_planeamento_intervalo(db, inicio, fim)["itens"]
    if not equipa_ids:
        return []

    itens_por_id = {}
    for equipa_id in equipa_ids:
        dashboard = obter_dashboard_planeamento_intervalo(db, inicio, fim, equipa_id=equipa_id)
        for item in dashboard["itens"]:
            itens_por_id[item["id"]] = item
    return sorted(
        itens_por_id.values(),
        key=lambda item: (item["data"], item["hora_inicio"] or "99:99", item["titulo"].lower()),
    )


def _obter_contexto_calendario(request: Request, db: Session, utilizador) -> dict:
    inicio, fim = _periodo_calendario(request)
    equipas = _equipas_visiveis(db, utilizador)
    ids_visiveis = [equipa.id for equipa in equipas]
    filtro_equipa = request.query_params.get("equipa_id", "").strip()
    equipa_id = int(filtro_equipa) if filtro_equipa.isdigit() and int(filtro_equipa) in ids_visiveis else None
    ids_consulta = [equipa_id] if equipa_id else (ids_visiveis if utilizador.perfil.value == "treinador" else None)
    itens = _obter_itens_calendario(db, inicio, fim, ids_consulta)
    itens_por_data: dict[date, list] = {}
    for item in itens:
        itens_por_data.setdefault(item["data"], []).append(item)
    dias = []
    cursor = inicio
    while cursor <= fim:
        dias.append(cursor)
        cursor += timedelta(days=1)
    meses = []
    cursor_mes = date(inicio.year, inicio.month, 1)
    limite_mes = date(fim.year, fim.month, 1)
    while cursor_mes <= limite_mes:
        semanas = []
        for semana in calendar.Calendar(firstweekday=0).monthdatescalendar(cursor_mes.year, cursor_mes.month):
            semanas.append([{
                "data": dia,
                "dia": dia.day,
                "do_mes": dia.month == cursor_mes.month,
                "itens": itens_por_data.get(dia, []),
            } for dia in semana])
        meses.append({"nome": calendar.month_name[cursor_mes.month], "ano": cursor_mes.year, "semanas": semanas})
        cursor_mes = date(cursor_mes.year + (cursor_mes.month == 12), 1 if cursor_mes.month == 12 else cursor_mes.month + 1, 1)

    return {
        "utilizador": utilizador,
        "hoje": date.today(),
        "periodo": {"inicio": inicio, "fim": fim, "label": f"{inicio:%d/%m/%Y} - {fim:%d/%m/%Y}"},
        "itens": itens,
        "itens_por_data": itens_por_data,
        "dias": dias,
        "meses_calendario": meses,
        "itens_administrativos": [item for item in itens if item["categoria"] not in {"treino", "jogo"}],
        "equipas": equipas,
        "equipa_id_selecionada": equipa_id,
        "estatisticas": {
            "total": len(itens),
            "treinos": sum(item["categoria"] == "treino" for item in itens),
            "jogos": sum(item["categoria"] == "jogo" for item in itens),
            "atividades": sum(item["categoria"] not in {"treino", "jogo"} for item in itens),
        },
        "agenda_contexto": {
            "global": True,
            "retorno": str(request.url),
            "data_inicio": inicio,
            "data_fim": fim,
        },
        "agenda_tipos": tipos_agenda_formulario(),
        "espacos_agenda": db.query(EspacoTreino).filter(EspacoTreino.ativo.is_(True)).order_by(EspacoTreino.nome).all(),
        "equipas_agenda": equipas,
    }


@router.get("/calendario", response_class=HTMLResponse)
def calendario_global(
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    """Apresenta a agenda operacional integrada do clube."""
    contexto = _obter_contexto_calendario(request, db, utilizador)
    return templates.TemplateResponse(request, "calendario.html", contexto)


@router.get("/calendario/pdf")
def exportar_pdf_calendario_global(
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    """Exporta a agenda operacional integrada numa tabela A4 legível."""
    contexto = _obter_contexto_calendario(request, db, utilizador)
    pdf_bytes = renderizar_pdf(request, "calendario_pdf.html", contexto)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=calendario_operacional.pdf"},
    )

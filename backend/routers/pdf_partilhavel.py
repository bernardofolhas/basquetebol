from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session

from auth_deps import exigir_autenticacao, exigir_coordenacao, exigir_operacao_desportiva, verificar_ou_negar_equipa
from database import get_db
from models.equipa import Equipa
from models.planeamento import Macrociclo, Mesociclo, Microciclo
from models.planeamento_clube import PlaneamentoClubeAnual, PlanoSemanalClube
from services.pdf_partilhavel_service import preparar_agenda_partilhavel
from services.pdf_service import renderizar_pdf


router = APIRouter(prefix="/partilha", tags=["PDF partilhável"])


def _ids_equipas_utilizador(utilizador) -> list[int] | None:
    if utilizador.perfil.value != "treinador":
        return None
    return [equipa.id for equipa in getattr(getattr(utilizador, "treinador", None), "equipas", [])]


def _responder(request, db, utilizador, *, titulo, data_inicio, data_fim, nome, equipa=None, categorias=None, equipa_ids=None, template="pdf_partilhavel.html"):
    if equipa_ids is None:
        equipa_ids = _ids_equipas_utilizador(utilizador)
    agenda = preparar_agenda_partilhavel(
        db,
        data_inicio,
        data_fim,
        equipa_ids=equipa_ids,
        categorias=categorias,
    )
    nome_treinador = getattr(getattr(utilizador, "treinador", None), "nome", None)
    if not nome_treinador and equipa and equipa.treinadores:
        nome_treinador = equipa.treinadores[0].nome
    pdf = renderizar_pdf(request, template, {
        "utilizador": utilizador,
        "titulo_documento": titulo,
        "equipa_documento": equipa,
        "agenda": agenda,
        "nome_treinador": nome_treinador or utilizador.nome,
        "hoje": date.today(),
    })
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={nome}"})


@router.get("/calendario/pdf")
def calendario_partilhavel(
    request: Request,
    inicio: date = Query(default_factory=date.today),
    fim: date | None = None,
    equipa_id: int | None = None,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_operacao_desportiva),
):
    fim = fim or (inicio + timedelta(days=30))
    equipa = None
    equipa_ids = None
    if equipa_id:
        verificar_ou_negar_equipa(utilizador, equipa_id, db)
        equipa = db.query(Equipa).filter(Equipa.id == equipa_id).first()
        equipa_ids = [equipa_id]
    return _responder(request, db, utilizador, titulo="Calendário operacional", data_inicio=inicio, data_fim=fim, nome="calendario_partilhavel.pdf", equipa=equipa, equipa_ids=equipa_ids, template="calendario_partilhavel_pdf.html")


@router.get("/equipas/{equipa_id}/jogos/pdf")
def jogos_partilhaveis(equipa_id: int, request: Request, inicio: date | None = None, fim: date | None = None, db: Session = Depends(get_db), utilizador=Depends(exigir_autenticacao)):
    verificar_ou_negar_equipa(utilizador, equipa_id, db)
    equipa = db.query(Equipa).filter(Equipa.id == equipa_id).first()
    if not equipa:
        return RedirectResponse("/equipas", status_code=303)
    inicio = inicio or date.today()
    fim = fim or (inicio + timedelta(days=180))
    return _responder(request, db, utilizador, titulo="Calendário de jogos", data_inicio=inicio, data_fim=fim, nome=f"jogos_{equipa_id}_partilhavel.pdf", equipa=equipa, equipa_ids=[equipa_id], categorias={"jogo"})


@router.get("/equipas/{equipa_id}/treinos/pdf")
def treinos_partilhaveis(equipa_id: int, request: Request, inicio: date | None = None, fim: date | None = None, db: Session = Depends(get_db), utilizador=Depends(exigir_autenticacao)):
    verificar_ou_negar_equipa(utilizador, equipa_id, db)
    equipa = db.query(Equipa).filter(Equipa.id == equipa_id).first()
    if not equipa:
        return RedirectResponse("/equipas", status_code=303)
    inicio = inicio or date.today()
    fim = fim or (inicio + timedelta(days=30))
    return _responder(request, db, utilizador, titulo="Agenda de treinos", data_inicio=inicio, data_fim=fim, nome=f"treinos_{equipa_id}_partilhavel.pdf", equipa=equipa, equipa_ids=[equipa_id], categorias={"treino"})


@router.get("/macrociclos/{macro_id}/pdf")
def macro_partilhavel(macro_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_autenticacao)):
    macro = db.query(Macrociclo).filter(Macrociclo.id == macro_id).first()
    if not macro:
        return RedirectResponse("/equipas", status_code=303)
    verificar_ou_negar_equipa(utilizador, macro.equipa_id, db)
    return _responder(request, db, utilizador, titulo=f"Macrociclo {macro.numero} · calendário", data_inicio=macro.data_inicio, data_fim=macro.data_fim, nome=f"macrociclo_{macro.id}_partilhavel.pdf", equipa=macro.equipa, equipa_ids=[macro.equipa_id])


@router.get("/mesociclos/{meso_id}/pdf")
def meso_partilhavel(meso_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_autenticacao)):
    meso = db.query(Mesociclo).filter(Mesociclo.id == meso_id).first()
    if not meso:
        return RedirectResponse("/equipas", status_code=303)
    equipa = meso.macrociclo.equipa
    verificar_ou_negar_equipa(utilizador, equipa.id, db)
    return _responder(request, db, utilizador, titulo=f"Mesociclo {meso.numero} · calendário", data_inicio=meso.data_inicio, data_fim=meso.data_fim, nome=f"mesociclo_{meso.id}_partilhavel.pdf", equipa=equipa, equipa_ids=[equipa.id])


@router.get("/microciclos/{micro_id}/pdf")
def micro_partilhavel(micro_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_autenticacao)):
    micro = db.query(Microciclo).filter(Microciclo.id == micro_id).first()
    if not micro:
        return RedirectResponse("/equipas", status_code=303)
    equipa = micro.mesociclo.macrociclo.equipa
    verificar_ou_negar_equipa(utilizador, equipa.id, db)
    return _responder(request, db, utilizador, titulo=f"Microciclo {micro.numero} · agenda semanal", data_inicio=micro.data_inicio, data_fim=micro.data_fim, nome=f"microciclo_{micro.id}_partilhavel.pdf", equipa=equipa, equipa_ids=[equipa.id])


@router.get("/anual/{anual_id}/pdf")
def anual_partilhavel(anual_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_coordenacao)):
    anual = db.query(PlaneamentoClubeAnual).filter(PlaneamentoClubeAnual.id == anual_id).first()
    if not anual:
        return RedirectResponse("/planeamento-clube/anual", status_code=303)
    return _responder(request, db, utilizador, titulo=f"Calendário anual · {anual.epoca}", data_inicio=anual.data_inicio, data_fim=anual.data_fim, nome=f"calendario_{anual.epoca}_partilhavel.pdf")


@router.get("/semanal/{semanal_id}/pdf")
def semanal_partilhavel(semanal_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_coordenacao)):
    semanal = db.query(PlanoSemanalClube).filter(PlanoSemanalClube.id == semanal_id).first()
    if not semanal:
        return RedirectResponse("/planeamento-clube/semanal", status_code=303)
    return _responder(request, db, utilizador, titulo=f"Agenda semanal · {semanal.titulo}", data_inicio=semanal.data_inicio, data_fim=semanal.data_fim, nome=f"semana_{semanal.id}_partilhavel.pdf")

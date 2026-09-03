from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, joinedload

from auth_deps import exigir_operacao_desportiva, verificar_ou_negar_equipa
from database import get_db
from models.equipa import Equipa
from models.estatistica import EventoEstatistica
from models.jogador import Jogador
from models.jogo import Convocado, Jogo
from paths import TEMPLATES_DIR
from services.auditoria_service import registar_auditoria
from services.estatistica_service import TIPOS_EVENTO, box_score_eventos, pontos_eventos, serializar_evento
from template_config import Jinja2Templates


router = APIRouter(prefix="/estatisticas")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


class EventoEntrada(BaseModel):
    client_uid: str = Field(min_length=8, max_length=80)
    jogador_id: int | None = None
    lado: str = "equipa"
    tipo: str
    periodo: int = Field(default=1, ge=1, le=20)
    segundos_restantes: int | None = Field(default=None, ge=0, le=3600)
    posicao_x: float | None = Field(default=None, ge=0, le=100)
    posicao_y: float | None = Field(default=None, ge=0, le=100)
    anulado: bool = False


class LoteEstatistica(BaseModel):
    eventos: list[EventoEntrada] = Field(default_factory=list, max_length=500)


def _jogo_acessivel(db: Session, jogo_id: int, utilizador) -> Jogo | None:
    jogo = db.query(Jogo).options(joinedload(Jogo.equipa)).filter(Jogo.id == jogo_id).first()
    if jogo:
        verificar_ou_negar_equipa(utilizador, jogo.equipa_id, db)
    return jogo


def _eventos_jogo(db: Session, jogo_id: int) -> list[EventoEstatistica]:
    return db.query(EventoEstatistica).options(joinedload(EventoEstatistica.jogador)).filter(
        EventoEstatistica.jogo_id == jogo_id
    ).order_by(EventoEstatistica.id).all()


def _pode_registar(utilizador) -> bool:
    return utilizador.perfil.value in {"administrador", "coordenador", "treinador", "superadministrador"}


@router.get("/equipas/{equipa_id}", response_class=HTMLResponse)
def dashboard_equipa(equipa_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_operacao_desportiva)):
    verificar_ou_negar_equipa(utilizador, equipa_id, db)
    equipa = db.query(Equipa).filter(Equipa.id == equipa_id).first()
    if not equipa:
        return RedirectResponse("/equipas", status_code=303)
    jogos = db.query(Jogo).filter(Jogo.equipa_id == equipa_id).order_by(Jogo.data.desc(), Jogo.hora.desc()).all()
    eventos = db.query(EventoEstatistica).filter(EventoEstatistica.equipa_id == equipa_id, EventoEstatistica.anulado.is_(False)).all()
    jogos_concluidos = [jogo for jogo in jogos if jogo.pontos_nos is not None and jogo.pontos_adversario is not None]
    resumo = {
        "jogos": len(jogos_concluidos),
        "vitorias": sum(jogo.pontos_nos > jogo.pontos_adversario for jogo in jogos_concluidos),
        "pontos": sum(jogo.pontos_nos or 0 for jogo in jogos_concluidos),
        "media": round(sum(jogo.pontos_nos or 0 for jogo in jogos_concluidos) / len(jogos_concluidos), 1) if jogos_concluidos else 0,
        "acoes": len(eventos),
    }
    eventos_por_jogo = {jogo.id: sum(evento.jogo_id == jogo.id for evento in eventos) for jogo in jogos}
    identidade = getattr(request.state, "identidade_clube", {}) or {}
    return templates.TemplateResponse(request, "estatisticas/dashboard.html", {
        "utilizador": utilizador, "equipa": equipa, "jogos": jogos,
        "resumo": resumo, "eventos_por_jogo": eventos_por_jogo,
        "pode_registar": _pode_registar(utilizador),
        "nome_clube": identidade.get("nome_curto") or identidade.get("nome_oficial") or equipa.nome,
    })


@router.get("/jogos/{jogo_id}", response_class=HTMLResponse)
def registo_jogo(jogo_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_operacao_desportiva)):
    jogo = _jogo_acessivel(db, jogo_id, utilizador)
    if not jogo:
        return RedirectResponse("/equipas", status_code=303)
    convocados_ids = [linha[0] for linha in db.query(Convocado.jogador_id).filter(Convocado.jogo_id == jogo.id).all()]
    jogadores_query = db.query(Jogador).filter(Jogador.equipa_id == jogo.equipa_id, Jogador.ativo.is_(True))
    if convocados_ids:
        jogadores_query = jogadores_query.filter(Jogador.id.in_(convocados_ids))
    jogadores = jogadores_query.order_by(Jogador.numero_camisola.asc().nullslast(), Jogador.nome).all()
    eventos = _eventos_jogo(db, jogo.id)
    identidade = getattr(request.state, "identidade_clube", {}) or {}
    return templates.TemplateResponse(request, "estatisticas/jogo.html", {
        "utilizador": utilizador, "equipa": jogo.equipa, "jogo": jogo,
        "jogadores": jogadores, "eventos": [serializar_evento(item) for item in eventos],
        "box_score": box_score_eventos(eventos), "pode_registar": _pode_registar(utilizador),
        "nome_clube": identidade.get("nome_curto") or identidade.get("nome_oficial") or jogo.equipa.nome,
    })


@router.post("/jogos/{jogo_id}/sincronizar")
def sincronizar_jogo(jogo_id: int, lote: LoteEstatistica, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_operacao_desportiva)):
    jogo = _jogo_acessivel(db, jogo_id, utilizador)
    if not jogo:
        return JSONResponse({"ok": False, "message": "Jogo não encontrado."}, status_code=404)
    if not _pode_registar(utilizador):
        return JSONResponse({"ok": False, "message": "Sem permissão para registar estatísticas."}, status_code=403)
    jogadores_validos = {item[0] for item in db.query(Jogador.id).filter(Jogador.equipa_id == jogo.equipa_id).all()}
    identificadores = [entrada.client_uid for entrada in lote.eventos]
    existentes = {
        evento.client_uid: evento
        for evento in db.query(EventoEstatistica).filter(EventoEstatistica.client_uid.in_(identificadores)).all()
    } if identificadores else {}
    criados = 0
    for entrada in lote.eventos:
        if entrada.tipo not in TIPOS_EVENTO or entrada.lado not in {"equipa", "adversario"}:
            return JSONResponse({"ok": False, "message": "Ação estatística inválida."}, status_code=400)
        if entrada.lado == "equipa" and (not entrada.jogador_id or entrada.jogador_id not in jogadores_validos):
            return JSONResponse({"ok": False, "message": "Seleciona um atleta válido."}, status_code=400)
        if (entrada.posicao_x is None) != (entrada.posicao_y is None):
            return JSONResponse({"ok": False, "message": "A posição da ação está incompleta."}, status_code=400)
        evento = existentes.get(entrada.client_uid)
        if evento:
            if evento.jogo_id != jogo.id:
                return JSONResponse({"ok": False, "message": "Identificador de sincronização inválido."}, status_code=409)
            evento.anulado = entrada.anulado
            continue
        evento = EventoEstatistica(
            client_uid=entrada.client_uid, clube_id=jogo.clube_id, equipa_id=jogo.equipa_id,
            jogo_id=jogo.id, jogador_id=entrada.jogador_id if entrada.lado == "equipa" else None,
            registado_por_id=utilizador.id, lado=entrada.lado, tipo=entrada.tipo,
            periodo=entrada.periodo, segundos_restantes=entrada.segundos_restantes,
            posicao_x=entrada.posicao_x, posicao_y=entrada.posicao_y,
            anulado=entrada.anulado,
        )
        db.add(evento)
        existentes[entrada.client_uid] = evento
        criados += 1
    db.flush()
    eventos = _eventos_jogo(db, jogo.id)
    jogo.pontos_nos = pontos_eventos(eventos, "equipa")
    jogo.pontos_adversario = pontos_eventos(eventos, "adversario")
    if criados:
        registar_auditoria(db, utilizador, "registar", "estatisticas_jogo", jogo.id, f"{criados} ação(ões) · {jogo.adversario}", request)
    db.commit()
    eventos = _eventos_jogo(db, jogo.id)
    return {
        "ok": True, "eventos": [serializar_evento(item) for item in eventos],
        "marcador": {"equipa": pontos_eventos(eventos, "equipa"), "adversario": pontos_eventos(eventos, "adversario")},
    }


@router.post("/jogos/{jogo_id}/reiniciar")
def reiniciar_estatistica_jogo(
    jogo_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_operacao_desportiva),
):
    jogo = _jogo_acessivel(db, jogo_id, utilizador)
    if not jogo:
        return JSONResponse({"ok": False, "message": "Jogo não encontrado."}, status_code=404)
    if not _pode_registar(utilizador):
        return JSONResponse({"ok": False, "message": "Sem permissão para eliminar estatísticas."}, status_code=403)

    total = db.query(EventoEstatistica).filter(EventoEstatistica.jogo_id == jogo.id).delete(
        synchronize_session=False
    )
    jogo.pontos_nos = None
    jogo.pontos_adversario = None
    registar_auditoria(
        db,
        utilizador,
        "eliminar",
        "estatisticas_jogo",
        jogo.id,
        f"Folha estatística reiniciada · {total} ação(ões) eliminada(s) · {jogo.adversario}",
        request,
    )
    db.commit()
    return {"ok": True, "eventos_eliminados": total, "marcador": {"equipa": 0, "adversario": 0}}

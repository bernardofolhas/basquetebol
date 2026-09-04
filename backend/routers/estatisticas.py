import hashlib
import json
from datetime import date

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, joinedload

from auth_deps import exigir_operacao_desportiva, verificar_ou_negar_equipa
from database import get_db
from models.equipa import Equipa
from config import config
from models.estatistica import EventoEstatistica, MapeamentoJogadorEstatistica
from models.jogador import Jogador
from models.jogo import Convocado, Jogo
from paths import TEMPLATES_DIR
from services.auditoria_service import registar_auditoria
from services.estatistica_service import (
    TIPOS_ALINHAMENTO,
    TIPOS_EVENTO,
    box_score_eventos,
    pontos_eventos,
    serializar_evento,
)
from services.fiba_stats_service import (
    ErroImportacaoFiba,
    MAX_FIBA_BYTES,
    interpretar_fiba,
    obter_estatistica_api,
    sugerir_mapeamentos,
)
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


def _jogadores_equipa(db: Session, equipa_id: int) -> list[Jogador]:
    return db.query(Jogador).filter(
        Jogador.equipa_id == equipa_id,
        Jogador.ativo.is_(True),
    ).order_by(Jogador.numero_camisola.asc().nullslast(), Jogador.nome).all()


def _mapeamentos_equipa(db: Session, equipa_id: int) -> dict[str, int]:
    return {
        item.identificador_externo: item.jogador_id
        for item in db.query(MapeamentoJogadorEstatistica).filter(
            MapeamentoJogadorEstatistica.equipa_id == equipa_id,
            MapeamentoJogadorEstatistica.fornecedor == "fiba",
        ).all()
    }


def _resumo_previsualizacao(db: Session, jogo: Jogo, dados: dict) -> dict:
    locais = _jogadores_equipa(db, jogo.equipa_id)
    mapeamentos = _mapeamentos_equipa(db, jogo.equipa_id)
    jogadores = sugerir_mapeamentos(dados["jogadores"], locais, mapeamentos)
    contagens: dict[str, int] = {}
    for evento in dados["eventos"]:
        contagens[evento["tipo"]] = contagens.get(evento["tipo"], 0) + 1
    return {
        "ok": True,
        "formato": dados["formato"],
        "equipas": dados["equipas"],
        "jogadores": jogadores,
        "eventos_suportados": len(dados["eventos"]),
        "eventos_ignorados": dados["eventos_ignorados"],
        "contagens": contagens,
        "amostra": dados["eventos"][:12],
    }


def _guardar_importacao(
    db: Session,
    jogo: Jogo,
    dados: dict,
    equipa_ficheiro: str,
    mapeamentos_json: str,
    origem: str,
    conteudo: bytes,
    utilizador,
    request: Request,
) -> dict:
    try:
        mapeamentos_recebidos = json.loads(mapeamentos_json or "{}")
        mapeamentos_recebidos = {str(chave): int(valor) for chave, valor in mapeamentos_recebidos.items() if valor}
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ErroImportacaoFiba("A associação dos atletas é inválida.") from exc

    jogadores_locais = {item.id: item for item in _jogadores_equipa(db, jogo.equipa_id)}
    if any(jogador_id not in jogadores_locais for jogador_id in mapeamentos_recebidos.values()):
        raise ErroImportacaoFiba("Foi selecionado um atleta que não pertence a esta equipa.")
    equipas_validas = {item["numero"] for item in dados["equipas"]}
    if equipas_validas and equipa_ficheiro not in equipas_validas:
        raise ErroImportacaoFiba("Seleciona qual é a equipa do clube no ficheiro.")

    jogadores_externos = {
        item["identificador"]: item
        for item in dados["jogadores"]
        if item["equipa_numero"] == equipa_ficheiro
    }
    for identificador, jogador_id in mapeamentos_recebidos.items():
        externo = jogadores_externos.get(identificador, {})
        mapeamento = db.query(MapeamentoJogadorEstatistica).filter(
            MapeamentoJogadorEstatistica.equipa_id == jogo.equipa_id,
            MapeamentoJogadorEstatistica.fornecedor == "fiba",
            MapeamentoJogadorEstatistica.identificador_externo == identificador,
        ).first()
        if not mapeamento:
            mapeamento = MapeamentoJogadorEstatistica(
                clube_id=jogo.clube_id,
                equipa_id=jogo.equipa_id,
                fornecedor="fiba",
                identificador_externo=identificador,
            )
            db.add(mapeamento)
        mapeamento.jogador_id = jogador_id
        mapeamento.nome_externo = externo.get("nome")
        mapeamento.numero_externo = externo.get("numero")

    importacao_uid = hashlib.sha256(conteudo).hexdigest()[:32]
    chaves = []
    for evento in dados["eventos"]:
        base = f"{jogo.id}:{evento['identificador_externo']}"
        chaves.append("fiba-" + hashlib.sha256(base.encode()).hexdigest()[:64])
    existentes = {
        item.client_uid: item
        for item in db.query(EventoEstatistica).filter(EventoEstatistica.client_uid.in_(chaves)).all()
    }
    criados = atualizados = sem_mapeamento = 0
    for evento, client_uid in zip(dados["eventos"], chaves):
        lado = "equipa" if evento["equipa_numero"] == equipa_ficheiro else "adversario"
        jogador_id = None
        if lado == "equipa" and evento["jogador_externo"]:
            jogador_id = mapeamentos_recebidos.get(evento["jogador_externo"])
            if not jogador_id:
                sem_mapeamento += 1
        registo = existentes.get(client_uid)
        if registo and registo.jogo_id != jogo.id:
            raise ErroImportacaoFiba("Foi detetado um identificador externo associado a outro jogo.")
        if not registo:
            registo = EventoEstatistica(
                client_uid=client_uid,
                clube_id=jogo.clube_id,
                equipa_id=jogo.equipa_id,
                jogo_id=jogo.id,
                registado_por_id=utilizador.id,
            )
            db.add(registo)
            criados += 1
        else:
            atualizados += 1
        registo.jogador_id = jogador_id
        registo.lado = lado
        registo.tipo = evento["tipo"]
        registo.periodo = evento["periodo"]
        registo.segundos_restantes = evento["segundos_restantes"]
        registo.posicao_x = evento["posicao_x"]
        registo.posicao_y = evento["posicao_y"]
        registo.origem = origem
        registo.identificador_externo = evento["identificador_externo"]
        registo.jogador_externo = evento["jogador_externo"] or None
        registo.subtipo = evento["subtipo"]
        registo.qualificadores = json.dumps(evento["qualificadores"], ensure_ascii=False)
        registo.importacao_uid = importacao_uid
        registo.anulado = evento["anulado"]

    db.flush()
    eventos = _eventos_jogo(db, jogo.id)
    jogo.pontos_nos = pontos_eventos(eventos, "equipa")
    jogo.pontos_adversario = pontos_eventos(eventos, "adversario")
    registar_auditoria(
        db,
        utilizador,
        "importar",
        "estatisticas_jogo",
        jogo.id,
        f"FIBA LiveStats · {criados} criada(s), {atualizados} atualizada(s) · {jogo.adversario}",
        request,
    )
    db.commit()
    return {
        "ok": True,
        "criadas": criados,
        "atualizadas": atualizados,
        "sem_mapeamento": sem_mapeamento,
        "ignoradas": dados["eventos_ignorados"],
        "marcador": {"equipa": jogo.pontos_nos, "adversario": jogo.pontos_adversario},
        "destino": f"/estatisticas/jogos/{jogo.id}?offline={utilizador.id}",
    }


@router.get("/equipas/{equipa_id}", response_class=HTMLResponse)
def dashboard_equipa(equipa_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_operacao_desportiva)):
    verificar_ou_negar_equipa(utilizador, equipa_id, db)
    equipa = db.query(Equipa).filter(Equipa.id == equipa_id).first()
    if not equipa:
        return RedirectResponse("/equipas", status_code=303)
    jogos = db.query(Jogo).filter(Jogo.equipa_id == equipa_id).order_by(Jogo.data.desc(), Jogo.hora.desc()).all()
    eventos = db.query(EventoEstatistica).filter(EventoEstatistica.equipa_id == equipa_id, EventoEstatistica.anulado.is_(False)).all()
    eventos_estatisticos = [evento for evento in eventos if evento.tipo not in TIPOS_ALINHAMENTO]
    jogos_concluidos = [jogo for jogo in jogos if jogo.pontos_nos is not None and jogo.pontos_adversario is not None]
    resumo = {
        "jogos": len(jogos_concluidos),
        "vitorias": sum(jogo.pontos_nos > jogo.pontos_adversario for jogo in jogos_concluidos),
        "pontos": sum(jogo.pontos_nos or 0 for jogo in jogos_concluidos),
        "media": round(sum(jogo.pontos_nos or 0 for jogo in jogos_concluidos) / len(jogos_concluidos), 1) if jogos_concluidos else 0,
        "acoes": len(eventos_estatisticos),
    }
    eventos_por_jogo = {
        jogo.id: sum(evento.jogo_id == jogo.id for evento in eventos_estatisticos)
        for jogo in jogos
    }
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


@router.get("/jogos/{jogo_id}/importar", response_class=HTMLResponse)
def importar_fiba(
    jogo_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_operacao_desportiva),
):
    jogo = _jogo_acessivel(db, jogo_id, utilizador)
    if not jogo:
        return RedirectResponse("/equipas", status_code=303)
    if not _pode_registar(utilizador):
        return RedirectResponse(f"/estatisticas/jogos/{jogo.id}", status_code=303)
    return templates.TemplateResponse(request, "estatisticas/importar_fiba.html", {
        "utilizador": utilizador,
        "equipa": jogo.equipa,
        "jogo": jogo,
        "jogadores": _jogadores_equipa(db, jogo.equipa_id),
        "api_configurada": bool(config.fiba_stats_api_url_template and config.fiba_stats_api_key),
    })


async def _ler_upload(ficheiro: UploadFile) -> tuple[bytes, str, str]:
    conteudo = await ficheiro.read(MAX_FIBA_BYTES + 1)
    if len(conteudo) > MAX_FIBA_BYTES:
        raise ErroImportacaoFiba("O ficheiro excede o limite de 8 MB.")
    return conteudo, ficheiro.filename or "estatistica.json", ficheiro.content_type or ""


@router.post("/jogos/{jogo_id}/fiba/previsualizar-ficheiro")
async def previsualizar_fiba_ficheiro(
    jogo_id: int,
    request: Request,
    ficheiro: UploadFile = File(...),
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_operacao_desportiva),
):
    jogo = _jogo_acessivel(db, jogo_id, utilizador)
    if not jogo or not _pode_registar(utilizador):
        return JSONResponse({"ok": False, "message": "Sem permissão para importar estatísticas."}, status_code=403)
    try:
        conteudo, nome, content_type = await _ler_upload(ficheiro)
        return _resumo_previsualizacao(db, jogo, interpretar_fiba(conteudo, nome, content_type))
    except ErroImportacaoFiba as exc:
        return JSONResponse({"ok": False, "message": str(exc)}, status_code=400)


@router.post("/jogos/{jogo_id}/fiba/importar-ficheiro")
async def importar_fiba_ficheiro(
    jogo_id: int,
    request: Request,
    ficheiro: UploadFile = File(...),
    equipa_ficheiro: str = Form(...),
    mapeamentos: str = Form("{}"),
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_operacao_desportiva),
):
    jogo = _jogo_acessivel(db, jogo_id, utilizador)
    if not jogo or not _pode_registar(utilizador):
        return JSONResponse({"ok": False, "message": "Sem permissão para importar estatísticas."}, status_code=403)
    try:
        conteudo, nome, content_type = await _ler_upload(ficheiro)
        dados = interpretar_fiba(conteudo, nome, content_type)
        return _guardar_importacao(db, jogo, dados, equipa_ficheiro, mapeamentos, "fiba_ficheiro", conteudo, utilizador, request)
    except ErroImportacaoFiba as exc:
        db.rollback()
        return JSONResponse({"ok": False, "message": str(exc)}, status_code=400)


@router.post("/jogos/{jogo_id}/fiba/previsualizar-api")
async def previsualizar_fiba_api(
    jogo_id: int,
    request: Request,
    identificador_jogo: str = Form(...),
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_operacao_desportiva),
):
    jogo = _jogo_acessivel(db, jogo_id, utilizador)
    if not jogo or not _pode_registar(utilizador):
        return JSONResponse({"ok": False, "message": "Sem permissão para importar estatísticas."}, status_code=403)
    try:
        conteudo, nome, content_type = await obter_estatistica_api(identificador_jogo)
        return _resumo_previsualizacao(db, jogo, interpretar_fiba(conteudo, nome, content_type))
    except ErroImportacaoFiba as exc:
        return JSONResponse({"ok": False, "message": str(exc)}, status_code=400)


@router.post("/jogos/{jogo_id}/fiba/importar-api")
async def importar_fiba_api(
    jogo_id: int,
    request: Request,
    identificador_jogo: str = Form(...),
    equipa_ficheiro: str = Form(...),
    mapeamentos: str = Form("{}"),
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_operacao_desportiva),
):
    jogo = _jogo_acessivel(db, jogo_id, utilizador)
    if not jogo or not _pode_registar(utilizador):
        return JSONResponse({"ok": False, "message": "Sem permissão para importar estatísticas."}, status_code=403)
    try:
        conteudo, nome, content_type = await obter_estatistica_api(identificador_jogo)
        dados = interpretar_fiba(conteudo, nome, content_type)
        return _guardar_importacao(db, jogo, dados, equipa_ficheiro, mapeamentos, "fiba_api", conteudo, utilizador, request)
    except ErroImportacaoFiba as exc:
        db.rollback()
        return JSONResponse({"ok": False, "message": str(exc)}, status_code=400)


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

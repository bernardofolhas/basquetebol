from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from template_config import Jinja2Templates
from sqlalchemy.orm import Session

from auth import verificar_acesso_equipa
from auth_deps import AcessoNegado, exigir_autenticacao
from database import get_db
from flash import set_flash
from models.equipa import Equipa
from models.playbook import Playbook, PassoSetPlay, SetPlay
from paths import TEMPLATES_DIR
from services.pdf_service import renderizar_pdf

router = APIRouter(prefix="/playbook")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _verificar_acesso_playbook(utilizador, equipa_id: int | None, db: Session) -> None:
    if not equipa_id or not verificar_acesso_equipa(utilizador, equipa_id, db):
        raise AcessoNegado("/equipas")


def _equipa_id_por_playbook(db: Session, playbook_id: int) -> int | None:
    p = db.query(Playbook).filter(Playbook.id == playbook_id).first()
    return p.equipa_id if p else None


def _equipa_id_por_setplay(db: Session, setplay_id: int) -> int | None:
    s = db.query(SetPlay).filter(SetPlay.id == setplay_id).first()
    return _equipa_id_por_playbook(db, s.playbook_id) if s else None


def _equipa_id_por_passo(db: Session, passo_id: int) -> int | None:
    p = db.query(PassoSetPlay).filter(PassoSetPlay.id == passo_id).first()
    return _equipa_id_por_setplay(db, p.setplay_id) if p else None


# ── PLAYBOOK DE UMA EQUIPA ────────────────────────────────────────────────────
@router.get("/equipas/{equipa_id}", response_class=HTMLResponse)
def playbook_equipa(equipa_id: int, request: Request, db: Session = Depends(get_db),
                    utilizador=Depends(exigir_autenticacao)):
    _verificar_acesso_playbook(utilizador, equipa_id, db)
    equipa = db.query(Equipa).filter(Equipa.id == equipa_id).first()
    if not equipa:
        return RedirectResponse(url="/equipas")

    playbook = db.query(Playbook).filter(Playbook.equipa_id == equipa_id).first()
    if not playbook:
        playbook = Playbook(equipa_id=equipa_id, nome=f"Playbook — {equipa.nome}")
        db.add(playbook)
        db.commit()
        db.refresh(playbook)

    categorias = ["Ataque", "Defesa", "Transição Ofensiva", "Transição Defensiva", "Zona", "Bola Parada", "Outro"]
    return templates.TemplateResponse(request, "playbook/lista.html", {
        "utilizador": utilizador,
        "equipa": equipa,
        "playbook": playbook,
        "setplays": playbook.setplays,
        "categorias": categorias,
    })


# ── CRIAR SETPLAY ────────────────────────────────────────────────────────────
@router.post("/equipas/{equipa_id}/setplays/novo")
async def criar_setplay(equipa_id: int, request: Request, db: Session = Depends(get_db),
                        utilizador=Depends(exigir_autenticacao),
                        nome: str = Form(...),
                        categoria: str = Form(""),
                        descricao: str = Form("")):
    _verificar_acesso_playbook(utilizador, equipa_id, db)
    playbook = db.query(Playbook).filter(Playbook.equipa_id == equipa_id).first()
    if not playbook:
        return RedirectResponse(url=f"/playbook/equipas/{equipa_id}", status_code=303)

    ordem = len(playbook.setplays)
    setplay = SetPlay(playbook_id=playbook.id, nome=nome, categoria=categoria or None,
                      descricao=descricao or None, ordem=ordem)
    db.add(setplay)
    db.commit()
    db.refresh(setplay)
    set_flash(request, f"Setplay '{nome}' criado.")
    return RedirectResponse(url=f"/playbook/setplays/{setplay.id}", status_code=303)


# ── DETALHE / EDITOR DE SETPLAY ───────────────────────────────────────────────
@router.get("/setplays/{setplay_id}", response_class=HTMLResponse)
def detalhe_setplay(setplay_id: int, request: Request, db: Session = Depends(get_db),
                    utilizador=Depends(exigir_autenticacao)):
    equipa_id = _equipa_id_por_setplay(db, setplay_id)
    _verificar_acesso_playbook(utilizador, equipa_id, db)

    setplay = db.query(SetPlay).filter(SetPlay.id == setplay_id).first()
    if not setplay:
        return RedirectResponse(url="/equipas")

    categorias = ["Ataque", "Defesa", "Transição Ofensiva", "Transição Defensiva", "Zona", "Bola Parada", "Outro"]
    return templates.TemplateResponse(request, "playbook/detalhe.html", {
        "utilizador": utilizador,
        "setplay": setplay,
        "playbook": setplay.playbook,
        "equipa": setplay.playbook.equipa,
        "passos": setplay.passos,
        "categorias": categorias,
    })


# ── EDITAR SETPLAY ────────────────────────────────────────────────────────────
@router.post("/setplays/{setplay_id}/editar")
async def editar_setplay(setplay_id: int, request: Request, db: Session = Depends(get_db),
                         utilizador=Depends(exigir_autenticacao),
                         nome: str = Form(...),
                         categoria: str = Form(""),
                         descricao: str = Form("")):
    equipa_id = _equipa_id_por_setplay(db, setplay_id)
    _verificar_acesso_playbook(utilizador, equipa_id, db)
    setplay = db.query(SetPlay).filter(SetPlay.id == setplay_id).first()
    if setplay:
        setplay.nome = nome
        setplay.categoria = categoria or None
        setplay.descricao = descricao or None
        db.commit()
        set_flash(request, "Setplay atualizado.")
    return RedirectResponse(url=f"/playbook/setplays/{setplay_id}", status_code=303)


# ── ELIMINAR SETPLAY ───────────────────────────────────────────────────────────
@router.post("/setplays/{setplay_id}/eliminar")
async def eliminar_setplay(setplay_id: int, request: Request, db: Session = Depends(get_db),
                           utilizador=Depends(exigir_autenticacao)):
    equipa_id = _equipa_id_por_setplay(db, setplay_id)
    _verificar_acesso_playbook(utilizador, equipa_id, db)
    setplay = db.query(SetPlay).filter(SetPlay.id == setplay_id).first()
    if setplay:
        playbook_id = setplay.playbook_id
        equipa_id_redirect = equipa_id
        db.delete(setplay)
        db.commit()
        set_flash(request, "Setplay eliminado.")
        return RedirectResponse(url=f"/playbook/equipas/{equipa_id_redirect}", status_code=303)
    return RedirectResponse(url="/equipas", status_code=303)


# ── ADICIONAR PASSO ────────────────────────────────────────────────────────────
@router.post("/setplays/{setplay_id}/passos/novo")
async def adicionar_passo(setplay_id: int, request: Request, db: Session = Depends(get_db),
                          utilizador=Depends(exigir_autenticacao)):
    equipa_id = _equipa_id_por_setplay(db, setplay_id)
    _verificar_acesso_playbook(utilizador, equipa_id, db)
    setplay = db.query(SetPlay).filter(SetPlay.id == setplay_id).first()
    if setplay:
        ordem = len(setplay.passos)
        passo = PassoSetPlay(setplay_id=setplay_id, ordem=ordem)
        db.add(passo)
        db.commit()
    return RedirectResponse(url=f"/playbook/setplays/{setplay_id}", status_code=303)


# ── ELIMINAR PASSO ─────────────────────────────────────────────────────────────
@router.post("/passos/{passo_id}/eliminar")
async def eliminar_passo(passo_id: int, request: Request, db: Session = Depends(get_db),
                         utilizador=Depends(exigir_autenticacao)):
    equipa_id = _equipa_id_por_passo(db, passo_id)
    _verificar_acesso_playbook(utilizador, equipa_id, db)
    passo = db.query(PassoSetPlay).filter(PassoSetPlay.id == passo_id).first()
    if passo:
        setplay_id = passo.setplay_id
        db.delete(passo)
        db.commit()
        # Re-number remaining steps
        restantes = db.query(PassoSetPlay).filter(
            PassoSetPlay.setplay_id == setplay_id
        ).order_by(PassoSetPlay.ordem).all()
        for i, p in enumerate(restantes):
            p.ordem = i
        db.commit()
        set_flash(request, "Passo eliminado.")
        return RedirectResponse(url=f"/playbook/setplays/{setplay_id}", status_code=303)
    return RedirectResponse(url="/equipas", status_code=303)


# ── GUARDAR OBSERVAÇÃO DO PASSO (form POST) ────────────────────────────────────
@router.post("/passos/{passo_id}/observacao")
async def guardar_observacao_passo(passo_id: int, request: Request, db: Session = Depends(get_db),
                                   utilizador=Depends(exigir_autenticacao),
                                   observacao: str = Form("")):
    equipa_id = _equipa_id_por_passo(db, passo_id)
    _verificar_acesso_playbook(utilizador, equipa_id, db)
    passo = db.query(PassoSetPlay).filter(PassoSetPlay.id == passo_id).first()
    if passo:
        passo.observacao = observacao or None
        db.commit()
    return RedirectResponse(url=f"/playbook/setplays/{passo.setplay_id}", status_code=303)


# ── GUARDAR DESENHO DO PASSO (AJAX JSON) ──────────────────────────────────────
@router.post("/passos/{passo_id}/desenho")
async def guardar_desenho_passo(passo_id: int, request: Request, db: Session = Depends(get_db),
                                utilizador=Depends(exigir_autenticacao)):
    from fastapi.responses import JSONResponse
    try:
        equipa_id = _equipa_id_por_passo(db, passo_id)
        _verificar_acesso_playbook(utilizador, equipa_id, db)
        body = await request.json()
        dados = body.get("dados", "")
        passo = db.query(PassoSetPlay).filter(PassoSetPlay.id == passo_id).first()
        if not passo:
            return JSONResponse({"sucesso": False, "erro": "Passo não encontrado"})
        passo.desenho = dados
        db.commit()
        return JSONResponse({"sucesso": True})
    except Exception as exc:
        return JSONResponse({"sucesso": False, "erro": str(exc)})


# ── MOVER PASSO PARA CIMA/BAIXO ───────────────────────────────────────────────
@router.post("/passos/{passo_id}/mover/{direcao}")
async def mover_passo(passo_id: int, direcao: str, request: Request,
                      db: Session = Depends(get_db), utilizador=Depends(exigir_autenticacao)):
    equipa_id = _equipa_id_por_passo(db, passo_id)
    _verificar_acesso_playbook(utilizador, equipa_id, db)
    passo = db.query(PassoSetPlay).filter(PassoSetPlay.id == passo_id).first()
    if not passo:
        return RedirectResponse(url="/equipas", status_code=303)

    passos = db.query(PassoSetPlay).filter(
        PassoSetPlay.setplay_id == passo.setplay_id
    ).order_by(PassoSetPlay.ordem).all()

    idx = next((i for i, p in enumerate(passos) if p.id == passo_id), None)
    if idx is None:
        return RedirectResponse(url=f"/playbook/setplays/{passo.setplay_id}", status_code=303)

    swap_idx = idx - 1 if direcao == "cima" else idx + 1
    if 0 <= swap_idx < len(passos):
        passos[idx].ordem, passos[swap_idx].ordem = passos[swap_idx].ordem, passos[idx].ordem
        db.commit()

    return RedirectResponse(url=f"/playbook/setplays/{passo.setplay_id}", status_code=303)


# ── EXPORTAR SETPLAY EM PDF ────────────────────────────────────────────────────
@router.get("/setplays/{setplay_id}/pdf")
def exportar_pdf_setplay(setplay_id: int, request: Request, db: Session = Depends(get_db),
                         utilizador=Depends(exigir_autenticacao)):
    equipa_id = _equipa_id_por_setplay(db, setplay_id)
    _verificar_acesso_playbook(utilizador, equipa_id, db)
    setplay = db.query(SetPlay).filter(SetPlay.id == setplay_id).first()
    if not setplay:
        return RedirectResponse(url="/equipas")

    pdf_bytes = renderizar_pdf(request, "playbook/pdf.html", {
        "setplay": setplay,
        "equipa": setplay.playbook.equipa,
        "passos": setplay.passos,
    })
    nome = f"setplay_{setplay.nome}_{setplay.playbook.equipa.nome}.pdf".replace(" ", "_")
    return Response(content=pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename={nome}"})

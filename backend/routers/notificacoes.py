from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from auth_deps import exigir_autenticacao
from database import get_db
from models.notificacao import Notificacao


router = APIRouter(prefix="/notificacoes")


@router.post("/{notificacao_id}/ler")
def marcar_como_lida(notificacao_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_autenticacao)):
    notificacao = db.query(Notificacao).filter(
        Notificacao.id == notificacao_id,
        Notificacao.utilizador_id == utilizador.id,
    ).first()
    if notificacao:
        notificacao.lida = True
        db.commit()
        return RedirectResponse(url=notificacao.link or "/dashboard", status_code=303)
    return RedirectResponse(url="/dashboard", status_code=303)


@router.post("/ler-todas")
def marcar_todas_como_lidas(request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_autenticacao)):
    db.query(Notificacao).filter(
        Notificacao.utilizador_id == utilizador.id,
        Notificacao.lida.is_(False),
    ).update({Notificacao.lida: True}, synchronize_session=False)
    db.commit()
    return RedirectResponse(url=request.headers.get("referer") or "/dashboard", status_code=303)


@router.post("/limpar-lidas")
def limpar_notificacoes_lidas(request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_autenticacao)):
    """Remove apenas avisos já consultados pelo próprio utilizador."""
    db.query(Notificacao).filter(
        Notificacao.utilizador_id == utilizador.id,
        Notificacao.lida.is_(True),
    ).delete(synchronize_session=False)
    db.commit()
    return RedirectResponse(url=request.headers.get("referer") or "/dashboard", status_code=303)

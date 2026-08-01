from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from auth import verificar_acesso_equipa
from auth_deps import exigir_autenticacao
from database import get_db
from models.equipa import Equipa
from models.jogador import Jogador
from models.jogo import Jogo
from paths import TEMPLATES_DIR
from template_config import Jinja2Templates


router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("/pesquisa", response_class=HTMLResponse)
def pesquisa_global(
    request: Request,
    q: str = Query("", max_length=80),
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    termo = q.strip()
    equipas = []
    jogadores = []
    jogos = []
    if len(termo) >= 2:
        padrao = f"%{termo}%"
        equipas = db.query(Equipa).filter(Equipa.nome.ilike(padrao)).order_by(Equipa.nome).limit(12).all()
        equipas = [equipa for equipa in equipas if verificar_acesso_equipa(utilizador, equipa.id, db)]
        ids = [equipa.id for equipa in equipas]
        jogadores_query = db.query(Jogador).filter(Jogador.nome.ilike(padrao))
        jogos_query = db.query(Jogo).filter(or_(Jogo.adversario.ilike(padrao), Jogo.competicao.ilike(padrao)))
        if utilizador.perfil.value == "treinador":
            ids_permitidos = [equipa.id for equipa in getattr(getattr(utilizador, "treinador", None), "equipas", [])]
            jogadores_query = jogadores_query.filter(Jogador.equipa_id.in_(ids_permitidos))
            jogos_query = jogos_query.filter(Jogo.equipa_id.in_(ids_permitidos))
        jogadores = jogadores_query.order_by(Jogador.nome).limit(12).all()
        jogos = jogos_query.order_by(Jogo.data.desc()).limit(12).all()

    return templates.TemplateResponse(request, "pesquisa.html", {
        "utilizador": utilizador,
        "q": termo,
        "equipas_resultado": equipas,
        "jogadores_resultado": jogadores,
        "jogos_resultado": jogos,
    })

# ─────────────────────────────────────────────────────────────
# ROUTER DE JOGOS
# Gere o calendário de jogos, resultados e convocatórias
# ─────────────────────────────────────────────────────────────

from fastapi import APIRouter, Request, Depends, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from database import get_db
from models.jogo import Jogo, Convocado
from models.equipa import Equipa
from models.jogador import Jogador

router = APIRouter(prefix="/jogos")
templates = Jinja2Templates(directory="../frontend/templates")


def obter_utilizador_atual(request: Request, db: Session):
    from auth import verificar_token
    from models.utilizador import Utilizador
    token = request.session.get("token")
    if not token:
        return None
    payload = verificar_token(token)
    if not payload:
        return None
    return db.query(Utilizador).filter(
        Utilizador.username == payload.get("sub")
    ).first()


# ─────────────────────────────────────────
# CALENDÁRIO DE JOGOS DE UMA EQUIPA
# URL: GET /jogos/equipas/{equipa_id}
# ─────────────────────────────────────────
@router.get("/equipas/{equipa_id}", response_class=HTMLResponse)
def calendario_jogos(equipa_id: int, request: Request, db: Session = Depends(get_db)):
    utilizador = obter_utilizador_atual(request, db)
    if not utilizador:
        return RedirectResponse(url="/login")

    equipa = db.query(Equipa).filter(Equipa.id == equipa_id).first()
    if not equipa:
        return RedirectResponse(url="/equipas")

    # Ordena os jogos por data
    jogos = db.query(Jogo).filter(
        Jogo.equipa_id == equipa_id
    ).order_by(Jogo.data).all()

    return templates.TemplateResponse(request, "jogos/calendario.html", {
        "utilizador": utilizador,
        "equipa": equipa,
        "jogos": jogos
    })


# ─────────────────────────────────────────
# CRIAR JOGO
# URL: POST /jogos/equipas/{equipa_id}/novo
# ─────────────────────────────────────────
@router.post("/equipas/{equipa_id}/novo")
async def criar_jogo(
    equipa_id: int,
    request: Request,
    db: Session = Depends(get_db),
    data: str = Form(...),
    hora: str = Form(""),
    local: str = Form(""),
    adversario: str = Form(...),
    competicao: str = Form(""),
    em_casa: str = Form("true"),
    observacoes: str = Form("")
):
    utilizador = obter_utilizador_atual(request, db)
    if not utilizador:
        return RedirectResponse(url="/login")

    from datetime import date
    jogo = Jogo(
        data=date.fromisoformat(data),
        hora=hora or None,
        local=local or None,
        adversario=adversario,
        competicao=competicao or None,
        # em_casa vem como string "true" ou "false" do formulário
        em_casa=em_casa == "true",
        observacoes=observacoes or None,
        equipa_id=equipa_id
    )

    db.add(jogo)
    db.commit()

    return RedirectResponse(url=f"/jogos/equipas/{equipa_id}", status_code=303)


# ─────────────────────────────────────────
# DETALHE DE UM JOGO
# URL: GET /jogos/{jogo_id}
# ─────────────────────────────────────────
@router.get("/{jogo_id}", response_class=HTMLResponse)
def detalhe_jogo(jogo_id: int, request: Request, db: Session = Depends(get_db)):
    utilizador = obter_utilizador_atual(request, db)
    if not utilizador:
        return RedirectResponse(url="/login")

    jogo = db.query(Jogo).filter(Jogo.id == jogo_id).first()
    if not jogo:
        return RedirectResponse(url="/equipas")

    # Jogadores da equipa para a convocatória
    jogadores = db.query(Jogador).filter(
        Jogador.equipa_id == jogo.equipa_id
    ).order_by(Jogador.nome).all()

    # IDs dos jogadores já convocados
    convocados_ids = {c.jogador_id for c in jogo.convocados}

    return templates.TemplateResponse(request, "jogos/detalhe.html", {
        "utilizador": utilizador,
        "jogo": jogo,
        "jogadores": jogadores,
        "convocados_ids": convocados_ids
    })


# ─────────────────────────────────────────
# REGISTAR RESULTADO
# URL: POST /jogos/{jogo_id}/resultado
# ─────────────────────────────────────────
@router.post("/{jogo_id}/resultado")
async def registar_resultado(
    jogo_id: int,
    request: Request,
    db: Session = Depends(get_db),
    pontos_nos: str = Form(""),
    pontos_adversario: str = Form("")
):
    utilizador = obter_utilizador_atual(request, db)
    if not utilizador:
        return RedirectResponse(url="/login")

    jogo = db.query(Jogo).filter(Jogo.id == jogo_id).first()
    if jogo:
        jogo.pontos_nos = int(pontos_nos) if pontos_nos else None
        jogo.pontos_adversario = int(pontos_adversario) if pontos_adversario else None
        db.commit()

    return RedirectResponse(url=f"/jogos/{jogo_id}", status_code=303)


# ─────────────────────────────────────────
# GUARDAR CONVOCATÓRIA
# URL: POST /jogos/{jogo_id}/convocatoria
# ─────────────────────────────────────────
@router.post("/{jogo_id}/convocatoria")
async def guardar_convocatoria(
    jogo_id: int,
    request: Request,
    db: Session = Depends(get_db),
    hora_encontro: str = Form(""),
    local_encontro: str = Form(""),
    observacoes: str = Form("")
):
    utilizador = obter_utilizador_atual(request, db)
    if not utilizador:
        return RedirectResponse(url="/login")

    # Lê os jogadores seleccionados manualmente
    # porque são checkboxes com nome dinâmico
    dados = await request.form()
    jogadores_ids = [
        int(k.replace("jogador_", ""))
        for k in dados.keys()
        if k.startswith("jogador_")
    ]

    # Remove convocados anteriores e recria
    db.query(Convocado).filter(Convocado.jogo_id == jogo_id).delete()

    for jogador_id in jogadores_ids:
        convocado = Convocado(
            jogo_id=jogo_id,
            jogador_id=jogador_id,
            hora_encontro=hora_encontro or None,
            local_encontro=local_encontro or None,
            observacoes=observacoes if observacoes and observacoes.strip() else None
        )
        db.add(convocado)

    db.commit()
    return RedirectResponse(url=f"/jogos/{jogo_id}", status_code=303)


from models.jogo import Jogo, Convocado, PlanoJogo

@router.get("/{jogo_id}/plano", response_class=HTMLResponse)
def pagina_plano_jogo(jogo_id: int, request: Request, db: Session = Depends(get_db)):
    utilizador = obter_utilizador_atual(request, db)
    if not utilizador:
        return RedirectResponse(url="/login")
    jogo = db.query(Jogo).filter(Jogo.id == jogo_id).first()
    if not jogo:
        return RedirectResponse(url="/equipas")
    jogadores = db.query(Jogador).filter(Jogador.equipa_id == jogo.equipa_id).order_by(Jogador.nome).all()
    plano = db.query(PlanoJogo).filter(PlanoJogo.jogo_id == jogo_id).first()
    return templates.TemplateResponse(request, "jogos/plano_jogo.html", {
        "utilizador": utilizador,
        "jogo": jogo,
        "jogadores": jogadores,
        "plano": plano
    })

@router.post("/{jogo_id}/plano")
async def guardar_plano_jogo(jogo_id: int, request: Request, db: Session = Depends(get_db)):
    utilizador = obter_utilizador_atual(request, db)
    if not utilizador:
        return RedirectResponse(url="/login")
    dados = await request.form()

    plano = db.query(PlanoJogo).filter(PlanoJogo.jogo_id == jogo_id).first()
    if not plano:
        plano = PlanoJogo(jogo_id=jogo_id)
        db.add(plano)

    campos = ['rotacoes','chaves_ataque','chaves_defesa','movimentos_ofensivos',
              'bloqueio_direto_lateral','bloqueio_direto_central','handoff',
              'indiretos_entrada','indiretos_saida','bola_dentro','situacoes_especiais','reflexao']

    for campo in campos:
        setattr(plano, campo, dados.get(campo) or None)

    for i in range(1, 6):
        val = dados.get(f'titular_{i}')
        setattr(plano, f'titular_{i}', int(val) if val else None)

    db.commit()
    return RedirectResponse(url=f"/jogos/{jogo_id}/plano", status_code=303)
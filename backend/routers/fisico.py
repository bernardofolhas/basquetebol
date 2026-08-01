from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from template_config import Jinja2Templates
from sqlalchemy.orm import Session

from auth_deps import exigir_autenticacao, verificar_ou_negar_equipa
from database import get_db
from flash import set_flash
from models.equipa import Equipa
from models.fisico import PlaneamentoFisico, TesteFisico
from models.jogador import Jogador
from paths import TEMPLATES_DIR

router = APIRouter(prefix="/fisico")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("/jogadores/{jogador_id}", response_class=HTMLResponse)
def testes_jogador(
    jogador_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    jogador = db.query(Jogador).filter(Jogador.id == jogador_id).first()
    if not jogador:
        return RedirectResponse(url="/jogadores")
    if not jogador.equipa_id:
        return RedirectResponse(url="/jogadores")
    verificar_ou_negar_equipa(utilizador, jogador.equipa_id, db)

    testes = db.query(TesteFisico).filter(
        TesteFisico.jogador_id == jogador_id
    ).order_by(TesteFisico.data.desc()).all()

    testes_por_tipo: dict = {}
    for teste in testes:
        testes_por_tipo.setdefault(teste.tipo_teste, []).append(teste)

    return templates.TemplateResponse(request, "fisico/testes.html", {
        "utilizador": utilizador,
        "jogador": jogador,
        "testes": testes,
        "testes_por_tipo": testes_por_tipo,
    })


@router.post("/jogadores/{jogador_id}/novo")
async def adicionar_teste(
    jogador_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
    data: str = Form(...),
    tipo_teste: str = Form(...),
    resultado: str = Form(""),
    unidade: str = Form(""),
    observacoes: str = Form(""),
):
    jogador = db.query(Jogador).filter(Jogador.id == jogador_id).first()
    if not jogador:
        return RedirectResponse(url="/jogadores")
    if not jogador.equipa_id:
        return RedirectResponse(url="/jogadores")
    verificar_ou_negar_equipa(utilizador, jogador.equipa_id, db)

    db.add(TesteFisico(
        data=date.fromisoformat(data),
        tipo_teste=tipo_teste,
        resultado=float(resultado) if resultado else None,
        unidade=unidade or None,
        observacoes=observacoes or None,
        jogador_id=jogador_id,
    ))
    db.commit()
    set_flash(request, f"Teste '{tipo_teste}' adicionado.")
    return RedirectResponse(url=f"/fisico/jogadores/{jogador_id}", status_code=303)


@router.get("/equipas/{equipa_id}", response_class=HTMLResponse)
def planeamento_equipa(
    equipa_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    verificar_ou_negar_equipa(utilizador, equipa_id, db)

    equipa = db.query(Equipa).filter(Equipa.id == equipa_id).first()
    if not equipa:
        return RedirectResponse(url="/equipas")

    planeamentos = db.query(PlaneamentoFisico).filter(
        PlaneamentoFisico.equipa_id == equipa_id
    ).order_by(PlaneamentoFisico.data_inicio.desc()).all()

    return templates.TemplateResponse(request, "fisico/planeamento.html", {
        "utilizador": utilizador,
        "equipa": equipa,
        "planeamentos": planeamentos,
    })


@router.post("/equipas/{equipa_id}/novo")
async def criar_planeamento(
    equipa_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
    data_inicio: str = Form(...),
    data_fim: str = Form(...),
    tipo: str = Form("Semanal"),
    resistencia: str = Form(""),
    velocidade: str = Form(""),
    forca: str = Form(""),
    flexibilidade: str = Form(""),
    coordenacao: str = Form(""),
    observacoes: str = Form(""),
):
    verificar_ou_negar_equipa(utilizador, equipa_id, db)

    db.add(PlaneamentoFisico(
        data_inicio=date.fromisoformat(data_inicio),
        data_fim=date.fromisoformat(data_fim),
        tipo=tipo,
        resistencia=resistencia or None,
        velocidade=velocidade or None,
        forca=forca or None,
        flexibilidade=flexibilidade or None,
        coordenacao=coordenacao or None,
        observacoes=observacoes or None,
        equipa_id=equipa_id,
    ))
    db.commit()
    set_flash(request, "Planeamento físico criado.")
    return RedirectResponse(url=f"/fisico/equipas/{equipa_id}", status_code=303)

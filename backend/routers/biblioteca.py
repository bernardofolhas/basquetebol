from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from template_config import Jinja2Templates
from sqlalchemy import or_
from sqlalchemy.orm import Session

from auth_deps import exigir_operacao_desportiva
from database import get_db
from flash import set_flash
from models.treino import BibliotecoExercicio
from paths import TEMPLATES_DIR

router = APIRouter(prefix="/biblioteca")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

CATEGORIAS = ["TIO", "TID", "TaIO", "TaID", "TCO", "TCD", "FIS"]


@router.get("", response_class=HTMLResponse)
def listar_biblioteca(
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_operacao_desportiva),
    categoria: str = Query(""),
    q: str = Query(""),
    tags: str = Query(""),
    desenho: str = Query(""),
):
    query = db.query(BibliotecoExercicio).order_by(BibliotecoExercicio.nome)
    if categoria:
        query = query.filter(BibliotecoExercicio.categoria == categoria)
    if q:
        termo = f"%{q}%"
        query = query.filter(or_(
            BibliotecoExercicio.nome.ilike(termo),
            BibliotecoExercicio.descricao.ilike(termo),
            BibliotecoExercicio.organizacao.ilike(termo),
            BibliotecoExercicio.coaching_points.ilike(termo),
            BibliotecoExercicio.tags.ilike(termo),
        ))
    if tags:
        query = query.filter(BibliotecoExercicio.tags.ilike(f"%{tags}%"))
    if desenho == "1":
        query = query.filter(BibliotecoExercicio.desenho.isnot(None))
    exercicios = query.all()
    return templates.TemplateResponse(request, "biblioteca/lista.html", {
        "utilizador": utilizador,
        "exercicios": exercicios,
        "categorias": CATEGORIAS,
        "categoria_activa": categoria,
        "pesquisa": q,
        "tags_activas": tags,
        "tem_desenho": desenho == "1",
    })


@router.post("/novo")
async def criar_exercicio(
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_operacao_desportiva),
    nome: str = Form(""),
    categoria: str = Form(""),
    descricao: str = Form(""),
    organizacao: str = Form(""),
    coaching_points: str = Form(""),
    tags: str = Form(""),
):
    nome = nome.strip()
    if not nome:
        set_flash(request, "O nome do exercício é obrigatório.", "error")
        return RedirectResponse(url="/biblioteca", status_code=303)

    ex = BibliotecoExercicio(
        nome=nome,
        categoria=categoria or None,
        descricao=descricao or None,
        organizacao=organizacao or None,
        coaching_points=coaching_points or None,
        tags=tags.strip() or None,
    )
    db.add(ex)
    db.commit()
    db.refresh(ex)
    set_flash(request, "Exercício adicionado à biblioteca.", "success")
    return RedirectResponse(url=f"/biblioteca/{ex.id}", status_code=303)


@router.get("/api/busca")
def api_buscar_exercicios(
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_operacao_desportiva),
    q: str = Query(""),
    categoria: str = Query(""),
    tags: str = Query(""),
):
    query = db.query(BibliotecoExercicio).order_by(BibliotecoExercicio.nome)
    if q:
        query = query.filter(BibliotecoExercicio.nome.ilike(f"%{q}%"))
    if categoria:
        query = query.filter(BibliotecoExercicio.categoria == categoria)
    if tags:
        query = query.filter(BibliotecoExercicio.tags.ilike(f"%{tags}%"))
    exercicios = query.limit(25).all()
    return JSONResponse([
        {
            "id": ex.id,
            "nome": ex.nome,
            "categoria": ex.categoria or "",
            "organizacao": ex.organizacao or "",
            "coaching_points": ex.coaching_points or "",
            "tags": ex.tags or "",
            "tem_desenho": bool(ex.desenho),
        }
        for ex in exercicios
    ])


@router.get("/{exercicio_id}", response_class=HTMLResponse)
def detalhe_exercicio(
    exercicio_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_operacao_desportiva),
):
    ex = db.query(BibliotecoExercicio).filter(BibliotecoExercicio.id == exercicio_id).first()
    if not ex:
        return RedirectResponse(url="/biblioteca")
    return templates.TemplateResponse(request, "biblioteca/detalhe.html", {
        "utilizador": utilizador,
        "ex": ex,
        "categorias": CATEGORIAS,
    })


@router.post("/{exercicio_id}/editar")
async def editar_exercicio(
    exercicio_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_operacao_desportiva),
    nome: str = Form(""),
    categoria: str = Form(""),
    descricao: str = Form(""),
    organizacao: str = Form(""),
    coaching_points: str = Form(""),
    tags: str = Form(""),
):
    ex = db.query(BibliotecoExercicio).filter(BibliotecoExercicio.id == exercicio_id).first()
    if ex:
        nome = nome.strip()
        if nome:
            ex.nome = nome
        ex.categoria = categoria or None
        ex.descricao = descricao or None
        ex.organizacao = organizacao or None
        ex.coaching_points = coaching_points or None
        ex.tags = tags.strip() or None
        db.commit()
        set_flash(request, "Exercício actualizado.", "success")
    return RedirectResponse(url=f"/biblioteca/{exercicio_id}", status_code=303)


@router.post("/{exercicio_id}/apagar")
async def apagar_exercicio_biblioteca(
    exercicio_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_operacao_desportiva),
):
    ex = db.query(BibliotecoExercicio).filter(BibliotecoExercicio.id == exercicio_id).first()
    if ex:
        db.delete(ex)
        db.commit()
        set_flash(request, "Exercício removido da biblioteca.", "success")
    return RedirectResponse(url="/biblioteca", status_code=303)


@router.post("/{exercicio_id}/desenho")
async def guardar_desenho_biblioteca(
    exercicio_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_operacao_desportiva),
):
    dados = await request.json()
    desenho_base64 = dados.get("dados")
    ex = db.query(BibliotecoExercicio).filter(BibliotecoExercicio.id == exercicio_id).first()
    if not ex:
        return JSONResponse({"sucesso": False, "erro": "Exercício não encontrado"})
    ex.desenho = desenho_base64
    db.commit()
    return JSONResponse({"sucesso": True})

# ─────────────────────────────────────────────────────────────
# ROUTER DE PLANO DE TREINO
# Gere a criação e edição de planos de treino detalhados
# Cada sessão de treino pode ter um plano com vários exercícios
# organizados em blocos (A, B, C, D)
# ─────────────────────────────────────────────────────────────

from fastapi import APIRouter, Request, Depends, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from database import get_db
from models.treino import PlanoTreino, ExercicioPlano, BibliotecoExercicio
from models.planeamento import SessaoTreino

# prefix="/treino" — todas as rotas começam com /treino
router = APIRouter(prefix="/treino")
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
# PÁGINA DO PLANO DE TREINO DE UMA SESSÃO
# URL: GET /treino/sessoes/{sessao_id}
# Se não existir plano, cria um automaticamente
# ─────────────────────────────────────────
@router.get("/sessoes/{sessao_id}", response_class=HTMLResponse)
def pagina_plano_treino(sessao_id: int, request: Request, db: Session = Depends(get_db)):
    utilizador = obter_utilizador_atual(request, db)
    if not utilizador:
        return RedirectResponse(url="/login")

    # Procura a sessão pelo ID
    sessao = db.query(SessaoTreino).filter(SessaoTreino.id == sessao_id).first()
    if not sessao:
        return RedirectResponse(url="/equipas")

    # Navega pela hierarquia para obter a equipa
    # sessao → microciclo → mesociclo → macrociclo → equipa
    equipa = sessao.microciclo.mesociclo.macrociclo.equipa

    # Verifica se já existe um plano para esta sessão
    plano = db.query(PlanoTreino).filter(
        PlanoTreino.sessao_id == sessao_id
    ).first()

    # Se não existir, cria um plano vazio automaticamente
    if not plano:
        plano = PlanoTreino(sessao_id=sessao_id)
        db.add(plano)
        db.commit()
        # db.refresh() recarrega o objecto com o id gerado pela BD
        db.refresh(plano)

    # Agrupa os exercícios por bloco para facilitar a apresentação
    # Usamos um dicionário: {"A": [ex1, ex2], "B": [ex3], ...}
    exercicios_por_bloco = {"A": [], "B": [], "C": [], "D": []}
    for ex in plano.exercicios:
        bloco = ex.bloco or "A"  # Se não tiver bloco, vai para o A
        if bloco in exercicios_por_bloco:
            exercicios_por_bloco[bloco].append(ex)

    return templates.TemplateResponse(request, "treino/plano.html", {
        "utilizador": utilizador,
        "sessao": sessao,
        "equipa": equipa,
        "plano": plano,
        "exercicios_por_bloco": exercicios_por_bloco
    })


# ─────────────────────────────────────────
# GUARDAR CABEÇALHO DO PLANO
# URL: POST /treino/planos/{plano_id}/cabecalho
# ─────────────────────────────────────────
@router.post("/planos/{plano_id}/cabecalho")
async def guardar_cabecalho(
    plano_id: int,
    request: Request,
    db: Session = Depends(get_db),
    hora_inicio: str = Form(""),
    escalao: str = Form(""),
    objectivos: str = Form("")
):
    utilizador = obter_utilizador_atual(request, db)
    if not utilizador:
        return RedirectResponse(url="/login")

    # Procura o plano e actualiza os campos do cabeçalho
    plano = db.query(PlanoTreino).filter(PlanoTreino.id == plano_id).first()
    if plano:
        plano.hora_inicio = hora_inicio or None
        plano.escalao = escalao or None
        plano.objectivos = objectivos or None
        db.commit()

    # Redireciona de volta para o plano
    return RedirectResponse(
        url=f"/treino/sessoes/{plano.sessao_id}",
        status_code=303
    )


# ─────────────────────────────────────────
# ADICIONAR EXERCÍCIO A UM BLOCO
# URL: POST /treino/planos/{plano_id}/exercicios
# ─────────────────────────────────────────
@router.post("/planos/{plano_id}/exercicios")
async def adicionar_exercicio(
    plano_id: int,
    request: Request,
    db: Session = Depends(get_db),
    bloco: str = Form("A"),
    nome: str = Form(""),
    categoria: str = Form(""),
    hora: str = Form(""),
    minutos: str = Form(""),
    organizacao: str = Form(""),
    coaching_points: str = Form("")
):
    utilizador = obter_utilizador_atual(request, db)
    if not utilizador:
        return RedirectResponse(url="/login")

    # Conta os exercícios já existentes neste bloco
    # para determinar a ordem do novo exercício
    total_no_bloco = db.query(ExercicioPlano).filter(
        ExercicioPlano.plano_id == plano_id,
        ExercicioPlano.bloco == bloco
    ).count()

    exercicio = ExercicioPlano(
        plano_id=plano_id,
        bloco=bloco,
        # A ordem é o total actual + 1
        ordem=total_no_bloco + 1,
        nome=nome or None,
        categoria=categoria or None,
        hora=hora or None,
        # int(x) if x else None — converte para inteiro só se não estiver vazio
        minutos=int(minutos) if minutos else None,
        organizacao=organizacao or None,
        coaching_points=coaching_points or None
    )

    db.add(exercicio)
    db.commit()

    # Procura o plano para obter o sessao_id para o redirecionamento
    plano = db.query(PlanoTreino).filter(PlanoTreino.id == plano_id).first()
    return RedirectResponse(
        url=f"/treino/sessoes/{plano.sessao_id}",
        status_code=303
    )


# ─────────────────────────────────────────
# APAGAR EXERCÍCIO
# URL: POST /treino/exercicios/{exercicio_id}/apagar
# ─────────────────────────────────────────
@router.post("/exercicios/{exercicio_id}/apagar")
async def apagar_exercicio(
    exercicio_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    utilizador = obter_utilizador_atual(request, db)
    if not utilizador:
        return RedirectResponse(url="/login")

    exercicio = db.query(ExercicioPlano).filter(
        ExercicioPlano.id == exercicio_id
    ).first()

    if exercicio:
        # Guarda o sessao_id antes de apagar para o redirecionamento
        sessao_id = exercicio.plano.sessao_id
        # db.delete() marca o objecto para remoção
        db.delete(exercicio)
        db.commit()
        return RedirectResponse(url=f"/treino/sessoes/{sessao_id}", status_code=303)

    return RedirectResponse(url="/equipas")


# ─────────────────────────────────────────
# GUARDAR REFLEXÃO DO PLANO
# URL: POST /treino/planos/{plano_id}/reflexao
# ─────────────────────────────────────────
@router.post("/planos/{plano_id}/reflexao")
async def guardar_reflexao(
    plano_id: int,
    request: Request,
    db: Session = Depends(get_db),
    reflexao: str = Form("")
):
    utilizador = obter_utilizador_atual(request, db)
    if not utilizador:
        return RedirectResponse(url="/login")

    plano = db.query(PlanoTreino).filter(PlanoTreino.id == plano_id).first()
    if plano:
        plano.reflexao = reflexao or None
        db.commit()

    return RedirectResponse(
        url=f"/treino/sessoes/{plano.sessao_id}",
        status_code=303
    )

# ─────────────────────────────────────────
# GUARDAR DESENHO DE UM EXERCÍCIO
# URL: POST /treino/exercicios/{exercicio_id}/desenho
# Recebe JSON com o desenho em base64 e guarda na BD
# ─────────────────────────────────────────
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import JSONResponse

@router.post("/exercicios/{exercicio_id}/desenho")
async def guardar_desenho(
    exercicio_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    utilizador = obter_utilizador_atual(request, db)
    if not utilizador:
        # JSONResponse devolve JSON em vez de HTML
        return JSONResponse({"sucesso": False, "erro": "Não autenticado"})

    # Lê o corpo do pedido como JSON
    # await request.json() é necessário porque o corpo é enviado como JSON
    dados = await request.json()
    numero = dados.get("numero")  # 1 ou 2
    desenho_base64 = dados.get("dados")  # A imagem em base64

    exercicio = db.query(ExercicioPlano).filter(
        ExercicioPlano.id == exercicio_id
    ).first()

    if not exercicio:
        return JSONResponse({"sucesso": False, "erro": "Exercício não encontrado"})

    # Guarda no campo correcto consoante o número do desenho
    if numero == 1:
        exercicio.desenho_1 = desenho_base64
    elif numero == 2:
        exercicio.desenho_2 = desenho_base64

    db.commit()
    return JSONResponse({"sucesso": True})
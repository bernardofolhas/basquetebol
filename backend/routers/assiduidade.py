# ─────────────────────────────────────────────────────────────
# ROUTER DE ASSIDUIDADE
# Gere o registo de presenças nas sessões de treino
# ─────────────────────────────────────────────────────────────

from fastapi import APIRouter, Request, Depends, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from database import get_db
from models.assiduidade import RegistoAssiduidade
from models.planeamento import SessaoTreino
from models.jogador import Jogador

# prefix="/assiduidade" — todas as rotas começam com /assiduidade
router = APIRouter(prefix="/assiduidade")
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
# PÁGINA DE ASSIDUIDADE DE UMA SESSÃO
# URL: GET /assiduidade/sessoes/{sessao_id}
# ─────────────────────────────────────────
@router.get("/sessoes/{sessao_id}", response_class=HTMLResponse)
def pagina_assiduidade(sessao_id: int, request: Request, db: Session = Depends(get_db)):
    utilizador = obter_utilizador_atual(request, db)
    if not utilizador:
        return RedirectResponse(url="/login")

    # Procura a sessão de treino pelo ID
    sessao = db.query(SessaoTreino).filter(SessaoTreino.id == sessao_id).first()
    if not sessao:
        return RedirectResponse(url="/equipas")

    # Obtém a equipa através da hierarquia:
    # sessao → microciclo → mesociclo → macrociclo → equipa
    # Cada ponto acede à relação definida nos modelos
    equipa = sessao.microciclo.mesociclo.macrociclo.equipa

    # Obtém todos os jogadores da equipa
    jogadores = db.query(Jogador).filter(
        Jogador.equipa_id == equipa.id
    ).order_by(Jogador.nome).all()

    # Verifica se já existem registos de assiduidade para esta sessão
    # Se não existirem, cria-os automaticamente para todos os jogadores
    registos_existentes = db.query(RegistoAssiduidade).filter(
        RegistoAssiduidade.sessao_id == sessao_id
    ).all()

    # Se ainda não há registos, cria um por cada jogador
    # com presente=False por defeito
    if not registos_existentes and jogadores:
        for jogador in jogadores:
            registo = RegistoAssiduidade(
                sessao_id=sessao_id,
                jogador_id=jogador.id,
                presente=False
            )
            # db.add() prepara o objecto para inserção
            db.add(registo)
        # db.commit() confirma todos os registos de uma vez
        db.commit()

    # Recarrega os registos após a criação
    registos = db.query(RegistoAssiduidade).filter(
        RegistoAssiduidade.sessao_id == sessao_id
    ).all()

    # Cria um dicionário {jogador_id: registo} para acesso rápido no template
    # Isto evita múltiplas pesquisas à base de dados no template
    registos_dict = {r.jogador_id: r for r in registos}

    # Calcula estatísticas de presença
    total_jogadores = len(jogadores)
    total_presentes = sum(1 for r in registos if r.presente)
    # Evita divisão por zero com o operador ternário
    percentagem = round((total_presentes / total_jogadores) * 100) if total_jogadores > 0 else 0

    return templates.TemplateResponse(request, "assiduidade/sessao.html", {
        "utilizador": utilizador,
        "sessao": sessao,
        "equipa": equipa,
        "jogadores": jogadores,
        "registos_dict": registos_dict,
        "total_presentes": total_presentes,
        "total_jogadores": total_jogadores,
        "percentagem": percentagem
    })


# ─────────────────────────────────────────
# GUARDAR ASSIDUIDADE
# URL: POST /assiduidade/sessoes/{sessao_id}
# ─────────────────────────────────────────
@router.post("/sessoes/{sessao_id}")
async def guardar_assiduidade(
    sessao_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    utilizador = obter_utilizador_atual(request, db)
    if not utilizador:
        return RedirectResponse(url="/login")

    # Lê os dados do formulário manualmente
    # porque temos campos dinâmicos (um por jogador)
    dados = await request.form()

    # Procura todos os registos desta sessão
    registos = db.query(RegistoAssiduidade).filter(
        RegistoAssiduidade.sessao_id == sessao_id
    ).all()

    # Para cada registo, verifica se o checkbox do jogador foi marcado
    for registo in registos:
        # O checkbox envia "on" se marcado, nada se não marcado
        # f"presente_{registo.jogador_id}" é o nome do campo no formulário
        presente = dados.get(f"presente_{registo.jogador_id}") == "on"
        motivo = dados.get(f"motivo_{registo.jogador_id}", "")

        # Actualiza o registo existente
        registo.presente = presente
        registo.motivo_falta = motivo if not presente and motivo else None

    # Guarda todas as alterações de uma vez
    db.commit()

    # Redireciona de volta para a página de assiduidade
    return RedirectResponse(url=f"/assiduidade/sessoes/{sessao_id}", status_code=303)
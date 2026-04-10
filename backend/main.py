from fastapi import FastAPI, Request, Depends, status, Form
from routers import treinadores
from fastapi.templating import Jinja2Templates
from routers import equipas
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session
from database import engine, get_db, Base
from auth import verificar_password, criar_token, verificar_token
from routers import jogadores
import models.jogador
import models.utilizador
import models.equipa
import models.treinador
# Importa o modelo de planeamento para que as tabelas sejam criadas
import models.planeamento
# Importa o router de planeamento
from routers import planeamento
# Importa o router de assiduidade
from routers import assiduidade
# Importa o router e modelo de plano de treino
from routers import treino
# Importa o modelo de jogo
import models.jogo
# Importa o router de jogos
from routers import jogos
import models.treino
import traceback

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Plataforma de Basquetebol")

# Sessões do lado do servidor — não dependem de cookies de terceiros
app.add_middleware(SessionMiddleware, secret_key="chave-secreta-sessao-123")

app.mount("/static", StaticFiles(directory="../frontend/static"), name="static")
templates = Jinja2Templates(directory="../frontend/templates")
app.include_router(equipas.router)
app.include_router(treinadores.router)
app.include_router(jogadores.router)
# Regista o router de planeamento na aplicação
app.include_router(planeamento.router)
# Regista o router de assiduidade na aplicação
app.include_router(assiduidade.router)
# Regista o router de treino na aplicação
app.include_router(treino.router)
# Regista o router de jogos
app.include_router(jogos.router)

def obter_utilizador_atual(request: Request, db: Session):
    token = request.session.get("token")
    if not token:
        return None
    payload = verificar_token(token)
    if not payload:
        return None
    from models.utilizador import Utilizador
    return db.query(Utilizador).filter(
        Utilizador.username == payload.get("sub")
    ).first()


@app.exception_handler(Exception)
async def erro_geral(request: Request, exc: Exception):
    traceback.print_exc()
    return HTMLResponse(f"<pre>{traceback.format_exc()}</pre>", status_code=500)


@app.get("/")
def raiz(request: Request, db: Session = Depends(get_db)):
    utilizador = obter_utilizador_atual(request, db)
    if utilizador:
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(request, "login.html")


@app.get("/login")
def pagina_login(request: Request, db: Session = Depends(get_db)):
    utilizador = obter_utilizador_atual(request, db)
    if utilizador:
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(request, "login.html")

@app.post("/login-form")
async def processar_login(
    request: Request,
    db: Session = Depends(get_db),
    username: str = Form(...),
    password: str = Form(...)
):
    from models.utilizador import Utilizador
    utilizador = db.query(Utilizador).filter(
        Utilizador.username == username
    ).first()

    if not utilizador or not verificar_password(password, utilizador.password_hash):
        return templates.TemplateResponse(request, "login.html", {
            "erro": "Username ou password incorretos."
        })

    token = criar_token({
        "sub": utilizador.username,
        "perfil": utilizador.perfil.value
    })

    request.session["token"] = token

    return templates.TemplateResponse(request, "dashboard.html", {
        "utilizador": utilizador
    })

    # Devolve uma página HTML que redireciona via JavaScript
    # Assim o browser mantém a sessão
    return HTMLResponse("""
        <!DOCTYPE html>
        <html>
        <body>
            <script>window.location.replace('/dashboard');</script>
        </body>
        </html>
    """)


@app.get("/dashboard")
def dashboard(request: Request, db: Session = Depends(get_db)):
    utilizador = obter_utilizador_atual(request, db)
    if not utilizador:
        return RedirectResponse(url="/login")

    from models.equipa import Equipa
    from models.treinador import Treinador
    from models.jogador import Jogador

    total_equipas = db.query(Equipa).count()
    total_treinadores = db.query(Treinador).count()
    total_jogadores = db.query(Jogador).count()

    return templates.TemplateResponse(request, "dashboard.html", {
        "utilizador": utilizador,
        "total_equipas": total_equipas,
        "total_treinadores": total_treinadores,
        "total_jogadores": total_jogadores
    })

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)


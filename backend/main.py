import os
from uuid import uuid4

from fastapi import Depends, FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from template_config import Jinja2Templates
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

import models.atividade
import models.avaliacao
import models.auditoria
import models.assiduidade
import models.clube
import models.atribuicao_espaco_semanal
import models.documento_jogador
import models.equipa
import models.espaco_agenda
import models.espaco_treino
import models.fisico
import models.jogador
import models.jogo
import models.notificacao
import models.historico_planeamento
import models.identidade_clube
import models.indisponibilidade_treinador
import models.planeamento
import models.planeamento_clube
import models.playbook
import models.questionario
import models.recuperacao_password
import models.relatorio_exportacao
import models.scouting
import models.treinador
import models.treino
import models.utilizador
from auth_deps import AcessoNegado, NaoAutenticado, SemPermissao
from config import config
from limiter import limiter
from csrf import CSRFMiddleware
from middleware_identidade import IdentidadeClubeMiddleware
from middleware_clube import ClubeContextoMiddleware
from middleware_navegacao import NavegacaoGlobalMiddleware
from middleware_retorno_criacao import RetornoAposCriacaoMiddleware
from middleware_cache import PaginasDinamicasSemCacheMiddleware
from middleware_staff import StaffPermissionsMiddleware
from database import (
    Base,
    actualizar_estrutura_assiduidade,
    actualizar_estrutura_campos_desenho,
    actualizar_estrutura_estatisticas,
    actualizar_estrutura_ficha_jogo,
    actualizar_estrutura_equipas_treino,
    actualizar_estrutura_staff,
    actualizar_estrutura_jogadores,
    actualizar_estrutura_perfis,
    actualizar_estrutura_escaloes,
    actualizar_estrutura_preferencias_dashboard,
    actualizar_estrutura_testes_fisicos,
    actualizar_estrutura_planeamento_clube,
    actualizar_estrutura_planeamento_equipa,
    actualizar_estrutura_mapa_conteudos,
    actualizar_estrutura_convocacoes_assiduidade,
    actualizar_estrutura_recuperacao_password,
    actualizar_estrutura_questionarios,
    actualizar_estrutura_objetivos_planeamento,
    actualizar_estrutura_playbook,
    base_dados_disponivel,
    engine,
    get_db,
    SessionLocal,
    validar_ligacao_base_dados,
)
from flash import FlashMiddleware
from formatacao import data_hora_pt, data_iso, data_pt, finalizar_valor_template
from logging_config import obter_logger
from paths import STATIC_DIR, TEMPLATES_DIR
from services.numeracao_planeamento_service import renumerar_todos_os_ciclos
from services.volume_sessao_service import sincronizar_volumes_automaticos
from routers import admin
from routers import agenda
from routers import avaliacoes
from routers import assiduidade
from routers import atividades
from routers import auth_web
from routers import biblioteca
from routers import calendario
from routers import espacos_agenda
from routers import estatisticas
from routers import exportacoes
from routers import dashboard
from routers import equipas
from routers import fisico
from routers import jogadores
from routers import jogos
from routers import notificacoes
from routers import identidade
from routers import secretaria
from routers import scouting
from routers import superadmin
from routers import planeamento
from routers import planeamento_clube
from routers import playbook
from routers import pesquisa
from routers import questionarios
from routers import pdf_partilhavel
from routers import treinadores
from routers import treino

logger = obter_logger(__name__)
VERSAO_APLICACAO = os.getenv("RAILWAY_GIT_COMMIT_SHA", "local")[:8]


def _validar_caminhos() -> None:
    """Confirma que as pastas críticas da aplicação existem."""
    for nome, caminho in {
        "templates": TEMPLATES_DIR,
        "ficheiros estáticos": STATIC_DIR,
    }.items():
        if not caminho.exists():
            raise RuntimeError(f"A pasta de {nome} não foi encontrada em: {caminho}")
    logger.info("Pastas de templates e ficheiros estáticos validadas com sucesso.")


try:
    _validar_caminhos()
    validar_ligacao_base_dados()
    Base.metadata.create_all(bind=engine)
    actualizar_estrutura_perfis()
    actualizar_estrutura_escaloes()
    actualizar_estrutura_preferencias_dashboard()
    actualizar_estrutura_testes_fisicos()
    actualizar_estrutura_equipas_treino()
    actualizar_estrutura_questionarios()
    actualizar_estrutura_staff()
    actualizar_estrutura_planeamento_clube()
    actualizar_estrutura_recuperacao_password()
    actualizar_estrutura_campos_desenho()
    actualizar_estrutura_objetivos_planeamento()
    actualizar_estrutura_playbook()
    actualizar_estrutura_planeamento_equipa()
    actualizar_estrutura_mapa_conteudos()
    actualizar_estrutura_assiduidade()
    actualizar_estrutura_convocacoes_assiduidade()
    actualizar_estrutura_jogadores()
    actualizar_estrutura_ficha_jogo()
    actualizar_estrutura_estatisticas()
    with SessionLocal() as db:
        from services.questionarios_service import sincronizar_acessos_atletas
        sincronizar_acessos_atletas(db)
        renumerar_todos_os_ciclos(db)
        sincronizar_volumes_automaticos(db)
        db.commit()
    logger.info("Infraestrutura inicial da aplicação preparada com sucesso.")
except Exception:
    logger.exception("Erro ao arrancar a aplicação: não foi possível preparar a infraestrutura inicial.")
    raise

app = FastAPI(title="Plataforma de Basquetebol")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Ordem de add_middleware: último adicionado = mais exterior = processa pedidos primeiro.
# Queremos: SessionMiddleware (exterior) → FlashMiddleware → CSRFMiddleware → app
# Por isso adicionamos na ordem inversa:
app.add_middleware(CSRFMiddleware)
app.add_middleware(IdentidadeClubeMiddleware)
app.add_middleware(NavegacaoGlobalMiddleware)
app.add_middleware(FlashMiddleware)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(StaffPermissionsMiddleware)
app.add_middleware(ClubeContextoMiddleware)
app.add_middleware(RetornoAposCriacaoMiddleware)
app.add_middleware(PaginasDinamicasSemCacheMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=config.session_secret_key,
    same_site=config.session_cookie_same_site,
    https_only=config.session_cookie_https_only,
    session_cookie=config.session_cookie_name,
    max_age=config.session_cookie_max_age_seconds,
    domain=config.session_cookie_domain,
)

try:
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    templates.env.filters["data_pt"] = data_pt
    templates.env.filters["data_hora_pt"] = data_hora_pt
    templates.env.filters["data_iso"] = data_iso
    templates.env.finalize = finalizar_valor_template
    logger.info("Templates e ficheiros estáticos configurados com sucesso.")
except Exception:
    logger.exception("Erro ao configurar templates ou ficheiros estáticos.")
    raise

app.include_router(biblioteca.router)
app.include_router(agenda.router)
app.include_router(avaliacoes.router)
app.include_router(espacos_agenda.router)
app.include_router(estatisticas.router)
app.include_router(exportacoes.router)
app.include_router(equipas.router)
app.include_router(treinadores.router)
app.include_router(jogadores.router)
app.include_router(planeamento.router)
app.include_router(planeamento_clube.router)
app.include_router(playbook.router)
app.include_router(pesquisa.router)
app.include_router(pdf_partilhavel.router)
app.include_router(questionarios.router)
app.include_router(assiduidade.router)
app.include_router(treino.router)
app.include_router(jogos.router)
app.include_router(scouting.router)
app.include_router(notificacoes.router)
app.include_router(identidade.router)
app.include_router(secretaria.router)
app.include_router(superadmin.router)
app.include_router(fisico.router)
app.include_router(admin.router)
app.include_router(dashboard.router)
app.include_router(atividades.router)
app.include_router(calendario.router)
app.include_router(auth_web.router)


@app.get("/service-worker.js", include_in_schema=False)
def service_worker():
    return FileResponse(
        STATIC_DIR / "js" / "service-worker.js",
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"},
    )


# ─────────────────────────────────────────────────────────────
# HANDLERS DE EXCEÇÕES DE AUTENTICAÇÃO/AUTORIZAÇÃO
# ─────────────────────────────────────────────────────────────

@app.exception_handler(NaoAutenticado)
async def handle_nao_autenticado(request: Request, exc: NaoAutenticado):
    return RedirectResponse(
        url="/login",
        status_code=302,
        headers={"X-Context-Redirect-Locked": "1"},
    )


@app.exception_handler(SemPermissao)
async def handle_sem_permissao(request: Request, exc: SemPermissao):
    if exc.status_code == 403:
        return JSONResponse(status_code=403, content={"detail": "Sem permissao para esta operacao."})
    return RedirectResponse(
        url=exc.redirect_para,
        status_code=exc.status_code,
        headers={"X-Context-Redirect-Locked": "1"},
    )


@app.exception_handler(AcessoNegado)
async def handle_acesso_negado(request: Request, exc: AcessoNegado):
    return RedirectResponse(
        url=exc.redirect_para,
        status_code=303,
        headers={"X-Context-Redirect-Locked": "1"},
    )


@app.exception_handler(Exception)
async def erro_geral(request: Request, exc: Exception):
    incidente = uuid4().hex[:8].upper()
    logger.error(
        "Incidente %s: erro não tratado ao processar o pedido '%s %s'.",
        incidente,
        request.method,
        request.url.path,
        exc_info=(type(exc), exc, exc.__traceback__),
    )

    if config.ambiente == "development":
        return HTMLResponse(
            f"<pre>{type(exc).__name__}: {exc!s}</pre>",
            status_code=500,
        )

    return HTMLResponse(
        "<main style='font-family:system-ui;max-width:680px;margin:12vh auto;padding:32px'>"
        "<h1>Não foi possível abrir esta página</h1>"
        "<p>O erro ficou registado e pode ser identificado pelo código "
        f"<strong>{incidente}</strong>.</p>"
        "<p><a href='javascript:history.back()'>Voltar à página anterior</a></p></main>",
        status_code=500,
        headers={"X-Incident-Id": incidente},
    )


@app.get("/")
def raiz(request: Request, db: Session = Depends(get_db)):
    request.session.clear()
    return templates.TemplateResponse(request, "login.html")


@app.get("/health")
def healthcheck():
    return {
        "estado": "ok",
        "servico": "basquetebol",
        "ambiente": config.ambiente,
        "versao": VERSAO_APLICACAO,
    }


@app.get("/ready")
def readiness():
    if not base_dados_disponivel():
        logger.warning("Readiness falhou: base de dados indisponível.")
        return JSONResponse(
            status_code=503,
            content={
                "estado": "indisponivel",
                "ambiente": config.ambiente,
                "base_dados": "indisponivel",
            },
        )

    return {
        "estado": "ok",
        "ambiente": config.ambiente,
        "base_dados": "ok",
    }

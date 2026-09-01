"""Scouting técnico por jogo: adversário, respostas da equipa e auto-scouting."""

from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from auth_deps import exigir_scouting, verificar_ou_negar_equipa
from database import get_db
from flash import set_flash
from models.jogo import Jogo
from models.scouting import RelatorioScouting, ScoutingAcao, ScoutingJogadorAdversario
from paths import TEMPLATES_DIR
from services.pdf_service import content_disposition_pdf, renderizar_pdf
from template_config import Jinja2Templates


router = APIRouter(prefix="/scouting")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

ESTADOS = {"rascunho", "publicado", "revisto", "arquivado"}
CONFIANCAS = {"baixa", "média", "alta"}


def _jogo_e_relatorio(db: Session, jogo_id: int, utilizador):
    jogo = db.query(Jogo).filter(Jogo.id == jogo_id).first()
    if not jogo:
        return None, None
    verificar_ou_negar_equipa(utilizador, jogo.equipa_id, db)
    relatorio = db.query(RelatorioScouting).filter(RelatorioScouting.jogo_id == jogo.id).first()
    if not relatorio:
        relatorio = RelatorioScouting(jogo_id=jogo.id)
        db.add(relatorio)
        db.commit()
        db.refresh(relatorio)
    return jogo, relatorio


def _obter_relatorio(db: Session, relatorio_id: int, utilizador):
    relatorio = db.query(RelatorioScouting).filter(RelatorioScouting.id == relatorio_id).first()
    if not relatorio or not relatorio.jogo:
        return None
    verificar_ou_negar_equipa(utilizador, relatorio.jogo.equipa_id, db)
    return relatorio


def _limpo(valor: str | None) -> str | None:
    valor = (valor or "").strip()
    return valor or None


def _contexto_pdf(request: Request, relatorio: RelatorioScouting, utilizador) -> dict:
    return {
        "utilizador": utilizador,
        "relatorio": relatorio,
        "jogo": relatorio.jogo,
        "equipa": relatorio.jogo.equipa,
        "nome_treinador": utilizador.nome,
        "data_exportacao": datetime.now().date(),
    }


@router.get("/jogos/{jogo_id}", response_class=HTMLResponse)
def pagina_scouting(
    jogo_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_scouting),
):
    jogo, relatorio = _jogo_e_relatorio(db, jogo_id, utilizador)
    if not jogo:
        return RedirectResponse(url="/equipas", status_code=303)
    return templates.TemplateResponse(request, "scouting/detalhe.html", {
        "utilizador": utilizador,
        "jogo": jogo,
        "relatorio": relatorio,
        "estados": ESTADOS,
        "confiancas": CONFIANCAS,
    })


@router.post("/{relatorio_id}/guardar")
async def guardar_scouting(
    relatorio_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_scouting),
):
    relatorio = _obter_relatorio(db, relatorio_id, utilizador)
    if not relatorio:
        return RedirectResponse(url="/equipas", status_code=303)
    dados = await request.form()
    campos = (
        "jogos_observados", "fontes", "identidade", "pontos_fortes", "vulnerabilidades",
        "ataque", "defesa", "transicao", "situacoes_especiais", "prioridades_defensivas",
        "prioridades_ofensivas", "primeiros_minutos", "plano_contingencia", "auto_scouting",
        "melhorias_prioritarias",
    )
    for campo in campos:
        setattr(relatorio, campo, _limpo(dados.get(campo)))
    confianca = dados.get("confianca")
    relatorio.confianca = confianca if confianca in CONFIANCAS else None
    db.commit()
    set_flash(request, "Scouting guardado.")
    return RedirectResponse(url=f"/scouting/jogos/{relatorio.jogo_id}", status_code=303)


@router.post("/{relatorio_id}/publicar")
def publicar_scouting(
    relatorio_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_scouting),
):
    relatorio = _obter_relatorio(db, relatorio_id, utilizador)
    if not relatorio:
        return RedirectResponse(url="/equipas", status_code=303)
    relatorio.estado = "publicado"
    relatorio.publicado_em = datetime.now()
    db.commit()
    set_flash(request, "Scouting publicado para a equipa técnica.")
    return RedirectResponse(url=f"/scouting/jogos/{relatorio.jogo_id}", status_code=303)


@router.post("/{relatorio_id}/jogadores/novo")
def adicionar_jogador_adversario(
    relatorio_id: int,
    request: Request,
    nome: str = Form(""),
    numero: str = Form(""),
    posicao: str = Form(""),
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_scouting),
):
    relatorio = _obter_relatorio(db, relatorio_id, utilizador)
    if not relatorio:
        return RedirectResponse(url="/equipas", status_code=303)
    if not _limpo(nome):
        set_flash(request, "Indica o nome do atleta adversário.", "error")
    else:
        db.add(ScoutingJogadorAdversario(
            relatorio_id=relatorio.id,
            ordem=len(relatorio.jogadores_adversarios),
            nome=_limpo(nome), numero=_limpo(numero), posicao=_limpo(posicao),
        ))
        db.commit()
        set_flash(request, "Atleta adversário adicionado.")
    return RedirectResponse(url=f"/scouting/jogos/{relatorio.jogo_id}", status_code=303)


@router.post("/jogadores/{jogador_id}/guardar")
async def guardar_jogador_adversario(
    jogador_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_scouting),
):
    jogador = db.query(ScoutingJogadorAdversario).filter(ScoutingJogadorAdversario.id == jogador_id).first()
    if not jogador or not _obter_relatorio(db, jogador.relatorio_id, utilizador):
        return RedirectResponse(url="/equipas", status_code=303)
    dados = await request.form()
    for campo in ("numero", "nome", "posicao", "papel", "mao_dominante", "como_pontua", "tendencias", "pontos_fortes", "limitacoes", "como_defender", "como_atacar"):
        setattr(jogador, campo, _limpo(dados.get(campo)))
    jogador.nome = jogador.nome or "Atleta adversário"
    jogador.prioridade = dados.get("prioridade") == "true"
    jogador.partilhavel = dados.get("partilhavel") == "true"
    db.commit()
    set_flash(request, "Perfil adversário atualizado.")
    return RedirectResponse(url=f"/scouting/jogos/{jogador.relatorio.jogo_id}", status_code=303)


@router.post("/jogadores/{jogador_id}/eliminar")
def eliminar_jogador_adversario(jogador_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_scouting)):
    jogador = db.query(ScoutingJogadorAdversario).filter(ScoutingJogadorAdversario.id == jogador_id).first()
    if not jogador or not _obter_relatorio(db, jogador.relatorio_id, utilizador):
        return RedirectResponse(url="/equipas", status_code=303)
    jogo_id = jogador.relatorio.jogo_id
    db.delete(jogador)
    db.commit()
    set_flash(request, "Atleta adversário removido.")
    return RedirectResponse(url=f"/scouting/jogos/{jogo_id}", status_code=303)


@router.post("/{relatorio_id}/acoes/nova")
def adicionar_acao(relatorio_id: int, request: Request, nome: str = Form(""), categoria: str = Form("Ataque"), db: Session = Depends(get_db), utilizador=Depends(exigir_scouting)):
    relatorio = _obter_relatorio(db, relatorio_id, utilizador)
    if not relatorio:
        return RedirectResponse(url="/equipas", status_code=303)
    if not _limpo(nome):
        set_flash(request, "Indica o nome da ação adversária.", "error")
    else:
        db.add(ScoutingAcao(relatorio_id=relatorio.id, ordem=len(relatorio.acoes), nome=_limpo(nome), categoria=_limpo(categoria) or "Ataque"))
        db.commit()
        set_flash(request, "Ação adversária adicionada.")
    return RedirectResponse(url=f"/scouting/jogos/{relatorio.jogo_id}", status_code=303)


@router.post("/acoes/{acao_id}/guardar")
async def guardar_acao(acao_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_scouting)):
    acao = db.query(ScoutingAcao).filter(ScoutingAcao.id == acao_id).first()
    if not acao or not _obter_relatorio(db, acao.relatorio_id, utilizador):
        return RedirectResponse(url="/equipas", status_code=303)
    dados = await request.form()
    for campo in ("categoria", "nome", "descricao", "resposta"):
        setattr(acao, campo, _limpo(dados.get(campo)))
    acao.nome = acao.nome or "Ação adversária"
    acao.categoria = acao.categoria or "Ataque"
    acao.prioridade = dados.get("prioridade") == "true"
    acao.partilhavel = dados.get("partilhavel") == "true"
    db.commit()
    set_flash(request, "Ação atualizada.")
    return RedirectResponse(url=f"/scouting/jogos/{acao.relatorio.jogo_id}", status_code=303)


@router.post("/acoes/{acao_id}/eliminar")
def eliminar_acao(acao_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_scouting)):
    acao = db.query(ScoutingAcao).filter(ScoutingAcao.id == acao_id).first()
    if not acao or not _obter_relatorio(db, acao.relatorio_id, utilizador):
        return RedirectResponse(url="/equipas", status_code=303)
    jogo_id = acao.relatorio.jogo_id
    db.delete(acao)
    db.commit()
    set_flash(request, "Ação removida.")
    return RedirectResponse(url=f"/scouting/jogos/{jogo_id}", status_code=303)


@router.get("/{relatorio_id}/pdf/{formato}")
def exportar_pdf_scouting(relatorio_id: int, formato: str, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_scouting)):
    relatorio = _obter_relatorio(db, relatorio_id, utilizador)
    if not relatorio:
        return RedirectResponse(url="/equipas", status_code=303)
    modelos = {
        "tecnico": ("scouting/pdf_tecnico.html", "Relatório de scouting"),
        "resumo": ("scouting/pdf_resumo_tecnico.html", "Resumo técnico"),
        "atletas-resumo": ("scouting/pdf_atletas_resumo.html", "Resumo para atletas"),
        "atletas": ("scouting/pdf_atletas.html", "Guia para atletas"),
    }
    if formato not in modelos:
        return RedirectResponse(url=f"/scouting/jogos/{relatorio.jogo_id}", status_code=303)
    modelo, titulo = modelos[formato]
    pdf = renderizar_pdf(request, modelo, _contexto_pdf(request, relatorio, utilizador))
    nome = f"{titulo} - {relatorio.jogo.equipa.nome} - {relatorio.jogo.adversario}".replace("/", "-")
    return Response(content=pdf, media_type="application/pdf", headers={"Content-Disposition": content_disposition_pdf(nome)})

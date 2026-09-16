"""Scouting técnico por jogo: adversário, respostas da equipa e auto-scouting."""

from datetime import datetime
import unicodedata

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from auth import verificar_acesso_equipa
from auth_deps import exigir_scouting, verificar_ou_negar_equipa
from clube_contexto import clube_atual_id
from database import get_db
from flash import set_flash
from models.jogo import Jogo
from models.scouting import (
    STAT_FIELDS,
    RelatorioScouting,
    ScoutingAcao,
    ScoutingAdversario,
    ScoutingAdversarioJogo,
    ScoutingEstatisticaJogo,
    ScoutingFichaIndividual,
    ScoutingItemBiblioteca,
    ScoutingJogador,
    ScoutingJogadorAdversario,
    ScoutingJogadorItem,
    ScoutingMediaEpoca,
    ScoutingZonaAcao,
)
from paths import TEMPLATES_DIR
from services.pdf_service import content_disposition_pdf, renderizar_pdf
from services.fotografia_jogador_service import apagar_fotografia, guardar_fotografia
from template_config import Jinja2Templates


router = APIRouter(prefix="/scouting")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

ESTADOS = {"rascunho", "publicado", "revisto", "arquivado"}
CONFIANCAS = {"baixa", "média", "alta"}
POSICOES = ("Base", "Extremo", "Poste")
ESTADOS_JOGADOR = ("ativo", "lesionado", "dúvida", "ausente")
CATEGORIAS_BIBLIOTECA = {
    "caracteristica": "Características",
    "movimento": "Movimentos preferenciais",
    "estrategia": "Estratégias defensivas",
}
ZONAS_CAMPO = (
    ("canto_esquerdo", "Canto esquerdo"), ("ala_esquerda", "Ala esquerda"),
    ("topo", "Topo"), ("ala_direita", "Ala direita"), ("canto_direito", "Canto direito"),
    ("poste_baixo_esquerdo", "Poste baixo esquerdo"), ("zona_central", "Zona central"),
    ("poste_baixo_direito", "Poste baixo direito"), ("aro", "Junto ao aro"),
)


def _normalizar(valor: str | None) -> str:
    texto = unicodedata.normalize("NFKD", (valor or "").strip().lower())
    return " ".join("".join(c for c in texto if not unicodedata.combining(c)).split())


def _clube_do_utilizador(utilizador) -> int:
    return clube_atual_id() if utilizador.perfil.value == "superadministrador" else utilizador.clube_id


def _float(valor) -> float | None:
    try:
        return float(str(valor).replace(",", ".")) if str(valor or "").strip() else None
    except ValueError:
        return None


def _int(valor) -> int | None:
    try:
        return int(valor) if str(valor or "").strip() else None
    except ValueError:
        return None


def _jogos_acessiveis(db: Session, utilizador) -> list[Jogo]:
    clube_id = _clube_do_utilizador(utilizador)
    jogos = db.query(Jogo).filter(Jogo.clube_id == clube_id).order_by(Jogo.data.desc()).all()
    return [jogo for jogo in jogos if verificar_acesso_equipa(utilizador, jogo.equipa_id, db)]


def _sincronizar_adversarios(db: Session, utilizador) -> None:
    clube_id = _clube_do_utilizador(utilizador)
    alterado = False
    for jogo in _jogos_acessiveis(db, utilizador):
        nome_normalizado = _normalizar(jogo.adversario)
        adversario = db.query(ScoutingAdversario).filter(
            ScoutingAdversario.clube_id == clube_id,
            ScoutingAdversario.nome_normalizado == nome_normalizado,
        ).first()
        if not adversario:
            adversario = ScoutingAdversario(clube_id=clube_id, nome=jogo.adversario.strip(), nome_normalizado=nome_normalizado)
            db.add(adversario)
            db.flush()
            alterado = True
        ligacao = db.query(ScoutingAdversarioJogo).filter(ScoutingAdversarioJogo.jogo_id == jogo.id).first()
        if not ligacao:
            db.add(ScoutingAdversarioJogo(clube_id=clube_id, adversario_id=adversario.id, jogo_id=jogo.id))
            alterado = True
    if alterado:
        db.commit()


def _adversario_acessivel(db: Session, adversario_id: int, utilizador) -> ScoutingAdversario | None:
    adversario = db.query(ScoutingAdversario).filter(ScoutingAdversario.id == adversario_id).first()
    if not adversario or adversario.clube_id != _clube_do_utilizador(utilizador):
        return None
    if not any(verificar_acesso_equipa(utilizador, ligacao.jogo.equipa_id, db) for ligacao in adversario.jogos if ligacao.jogo):
        return None
    return adversario


def _jogador_acessivel(db: Session, jogador_id: int, utilizador) -> ScoutingJogador | None:
    jogador = db.query(ScoutingJogador).filter(ScoutingJogador.id == jogador_id).first()
    return jogador if jogador and _adversario_acessivel(db, jogador.adversario_id, utilizador) else None


def _contexto_departamento(request, utilizador, adversario=None, **extra):
    contexto = {
        "utilizador": utilizador, "adversario": adversario, "equipa": None,
        "posicoes": POSICOES, "estados_jogador": ESTADOS_JOGADOR,
        "categorias_biblioteca": CATEGORIAS_BIBLIOTECA, "zonas_campo": ZONAS_CAMPO,
    }
    contexto.update(extra)
    return contexto


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


@router.get("", response_class=HTMLResponse)
def departamento_scouting(request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_scouting)):
    _sincronizar_adversarios(db, utilizador)
    acessiveis = []
    for adversario in db.query(ScoutingAdversario).filter(
        ScoutingAdversario.clube_id == _clube_do_utilizador(utilizador)
    ).order_by(ScoutingAdversario.nome).all():
        jogos = [ligacao.jogo for ligacao in adversario.jogos if ligacao.jogo and verificar_acesso_equipa(utilizador, ligacao.jogo.equipa_id, db)]
        if jogos:
            adversario.jogos_acessiveis = sorted(jogos, key=lambda jogo: jogo.data, reverse=True)
            acessiveis.append(adversario)
    return templates.TemplateResponse(request, "scouting/index.html", _contexto_departamento(
        request, utilizador, adversarios=acessiveis, total_jogadores=sum(len(item.jogadores) for item in acessiveis)
    ))


@router.get("/adversarios/{adversario_id}")
def abrir_adversario(adversario_id: int):
    return RedirectResponse(url=f"/scouting/adversarios/{adversario_id}/resumo", status_code=303)


@router.get("/adversarios/{adversario_id}/{separador}", response_class=HTMLResponse)
def separador_adversario(adversario_id: int, separador: str, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_scouting)):
    if separador not in {"resumo", "roster", "individual", "coletivo", "relatorios"}:
        return RedirectResponse(url=f"/scouting/adversarios/{adversario_id}/resumo", status_code=303)
    adversario = _adversario_acessivel(db, adversario_id, utilizador)
    if not adversario:
        return RedirectResponse(url="/scouting", status_code=303)
    jogos = sorted([ligacao.jogo for ligacao in adversario.jogos if ligacao.jogo], key=lambda jogo: jogo.data, reverse=True)
    if separador == "roster":
        grupos = {posicao: [j for j in adversario.jogadores if j.posicao_principal == posicao] for posicao in POSICOES}
        return templates.TemplateResponse(request, "scouting/roster.html", _contexto_departamento(
            request, utilizador, adversario, separador=separador, grupos=grupos, jogos=jogos
        ))
    if separador == "individual":
        return templates.TemplateResponse(request, "scouting/individual_lista.html", _contexto_departamento(
            request, utilizador, adversario, separador=separador, jogadores=adversario.jogadores, jogos=jogos
        ))
    if separador == "resumo":
        return templates.TemplateResponse(request, "scouting/resumo.html", _contexto_departamento(
            request, utilizador, adversario, separador=separador, jogos=jogos
        ))
    return templates.TemplateResponse(request, "scouting/em_desenvolvimento.html", _contexto_departamento(
        request, utilizador, adversario, separador=separador, titulo="Scouting coletivo" if separador == "coletivo" else "Relatórios"
    ))


@router.post("/adversarios/{adversario_id}/jogadores")
async def criar_jogador(adversario_id: int, request: Request, fotografia: UploadFile | None = File(None), db: Session = Depends(get_db), utilizador=Depends(exigir_scouting)):
    adversario = _adversario_acessivel(db, adversario_id, utilizador)
    if not adversario:
        return RedirectResponse(url="/scouting", status_code=303)
    dados = await request.form()
    nome = _limpo(dados.get("nome"))
    posicao = dados.get("posicao_principal")
    if not nome or posicao not in POSICOES:
        set_flash(request, "Preenche o nome e uma posição principal válida.", "error")
        return RedirectResponse(url=f"/scouting/adversarios/{adversario.id}/roster", status_code=303)
    try:
        foto = await guardar_fotografia(fotografia)
    except ValueError as erro:
        set_flash(request, str(erro), "error")
        return RedirectResponse(url=f"/scouting/adversarios/{adversario.id}/roster", status_code=303)
    jogador = ScoutingJogador(
        clube_id=adversario.clube_id, adversario_id=adversario.id, fotografia=foto, nome=nome,
        numero=_limpo(dados.get("numero")), idade=_int(dados.get("idade")), posicao_principal=posicao,
        posicao_alternativa=dados.get("posicao_alternativa") if dados.get("posicao_alternativa") in POSICOES else None,
        altura_cm=_float(dados.get("altura_cm")), peso_kg=_float(dados.get("peso_kg")),
        equipa_anterior=_limpo(dados.get("equipa_anterior")),
        estado=dados.get("estado") if dados.get("estado") in ESTADOS_JOGADOR else "ativo",
        mao_dominante=_limpo(dados.get("mao_dominante")), observacoes=_limpo(dados.get("observacoes")),
    )
    db.add(jogador)
    db.flush()
    db.add(ScoutingFichaIndividual(clube_id=adversario.clube_id, jogador_id=jogador.id))
    db.add(ScoutingMediaEpoca(clube_id=adversario.clube_id, jogador_id=jogador.id))
    db.commit()
    set_flash(request, "Atleta adicionado ao roster e ficha individual criada.")
    return RedirectResponse(url=f"/scouting/adversarios/{adversario.id}/roster", status_code=303)


@router.post("/roster/{jogador_id}/guardar")
async def editar_jogador(jogador_id: int, request: Request, fotografia: UploadFile | None = File(None), db: Session = Depends(get_db), utilizador=Depends(exigir_scouting)):
    jogador = _jogador_acessivel(db, jogador_id, utilizador)
    if not jogador:
        return RedirectResponse(url="/scouting", status_code=303)
    dados = await request.form()
    nome = _limpo(dados.get("nome"))
    posicao = dados.get("posicao_principal")
    if not nome or posicao not in POSICOES:
        set_flash(request, "Preenche o nome e uma posição principal válida.", "error")
        return RedirectResponse(url=f"/scouting/adversarios/{jogador.adversario_id}/roster", status_code=303)
    try:
        nova_foto = await guardar_fotografia(fotografia)
    except ValueError as erro:
        set_flash(request, str(erro), "error")
        return RedirectResponse(url=f"/scouting/adversarios/{jogador.adversario_id}/roster", status_code=303)
    foto_antiga = jogador.fotografia
    if dados.get("remover_fotografia") == "true":
        jogador.fotografia = None
    if nova_foto:
        jogador.fotografia = nova_foto
    jogador.nome, jogador.numero, jogador.idade = nome, _limpo(dados.get("numero")), _int(dados.get("idade"))
    jogador.posicao_principal = posicao
    jogador.posicao_alternativa = dados.get("posicao_alternativa") if dados.get("posicao_alternativa") in POSICOES else None
    jogador.altura_cm, jogador.peso_kg = _float(dados.get("altura_cm")), _float(dados.get("peso_kg"))
    jogador.equipa_anterior = _limpo(dados.get("equipa_anterior"))
    jogador.estado = dados.get("estado") if dados.get("estado") in ESTADOS_JOGADOR else "ativo"
    jogador.mao_dominante, jogador.observacoes = _limpo(dados.get("mao_dominante")), _limpo(dados.get("observacoes"))
    db.commit()
    if foto_antiga and (nova_foto or dados.get("remover_fotografia") == "true"):
        apagar_fotografia(foto_antiga)
    set_flash(request, "Dados do atleta atualizados.")
    return RedirectResponse(url=f"/scouting/adversarios/{jogador.adversario_id}/roster", status_code=303)


@router.post("/roster/{jogador_id}/eliminar")
def eliminar_jogador_roster(jogador_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_scouting)):
    jogador = _jogador_acessivel(db, jogador_id, utilizador)
    if not jogador:
        return RedirectResponse(url="/scouting", status_code=303)
    adversario_id, foto = jogador.adversario_id, jogador.fotografia
    db.delete(jogador)
    db.commit()
    apagar_fotografia(foto)
    set_flash(request, "Atleta removido do roster.")
    return RedirectResponse(url=f"/scouting/adversarios/{adversario_id}/roster", status_code=303)


@router.get("/jogadores/{jogador_id}", response_class=HTMLResponse)
def ficha_individual(jogador_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_scouting)):
    jogador = _jogador_acessivel(db, jogador_id, utilizador)
    if not jogador:
        return RedirectResponse(url="/scouting", status_code=303)
    if not jogador.ficha:
        db.add(ScoutingFichaIndividual(clube_id=jogador.clube_id, jogador_id=jogador.id))
    if not jogador.media_epoca:
        db.add(ScoutingMediaEpoca(clube_id=jogador.clube_id, jogador_id=jogador.id))
    db.commit()
    biblioteca = db.query(ScoutingItemBiblioteca).filter(ScoutingItemBiblioteca.clube_id == jogador.clube_id).order_by(ScoutingItemBiblioteca.nome).all()
    jogos = sorted([ligacao.jogo for ligacao in jogador.adversario.jogos if ligacao.jogo], key=lambda jogo: jogo.data, reverse=True)
    return templates.TemplateResponse(request, "scouting/individual.html", _contexto_departamento(
        request, utilizador, jogador.adversario, separador="individual", jogador=jogador, biblioteca=biblioteca,
        jogos=jogos, stat_fields=STAT_FIELDS
    ))


@router.post("/jogadores/{jogador_id}/resumo")
async def guardar_resumo_individual(jogador_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_scouting)):
    jogador = _jogador_acessivel(db, jogador_id, utilizador)
    if not jogador:
        return RedirectResponse(url="/scouting", status_code=303)
    dados = await request.form()
    jogador.ficha.resumo = _limpo(dados.get("resumo"))
    db.commit()
    set_flash(request, "Resumo individual guardado.")
    return RedirectResponse(url=f"/scouting/jogadores/{jogador.id}", status_code=303)


@router.post("/jogadores/{jogador_id}/media")
async def guardar_media(jogador_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_scouting)):
    jogador = _jogador_acessivel(db, jogador_id, utilizador)
    if not jogador:
        return RedirectResponse(url="/scouting", status_code=303)
    dados = await request.form()
    media = jogador.media_epoca or ScoutingMediaEpoca(clube_id=jogador.clube_id, jogador_id=jogador.id)
    db.add(media)
    for campo in STAT_FIELDS:
        setattr(media, campo, _float(dados.get(campo)))
    db.commit()
    set_flash(request, "Média da época atualizada.")
    return RedirectResponse(url=f"/scouting/jogadores/{jogador.id}#estatisticas", status_code=303)


@router.post("/jogadores/{jogador_id}/estatisticas")
async def guardar_estatistica(jogador_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_scouting)):
    jogador = _jogador_acessivel(db, jogador_id, utilizador)
    if not jogador:
        return RedirectResponse(url="/scouting", status_code=303)
    dados = await request.form()
    jogo_id = _int(dados.get("jogo_id"))
    jogo = next((ligacao.jogo for ligacao in jogador.adversario.jogos if ligacao.jogo_id == jogo_id), None)
    if not jogo:
        set_flash(request, "Seleciona um jogo associado a este adversário.", "error")
        return RedirectResponse(url=f"/scouting/jogadores/{jogador.id}#estatisticas", status_code=303)
    registo = db.query(ScoutingEstatisticaJogo).filter(ScoutingEstatisticaJogo.jogador_id == jogador.id, ScoutingEstatisticaJogo.jogo_id == jogo.id).first()
    if not registo:
        registo = ScoutingEstatisticaJogo(clube_id=jogador.clube_id, jogador_id=jogador.id, jogo_id=jogo.id, data=jogo.data, adversario=jogo.equipa.nome, competicao=jogo.competicao)
        db.add(registo)
    for campo in STAT_FIELDS:
        setattr(registo, campo, _float(dados.get(campo)))
    db.commit()
    set_flash(request, "Estatísticas do jogo guardadas.")
    return RedirectResponse(url=f"/scouting/jogadores/{jogador.id}#estatisticas", status_code=303)


@router.post("/estatisticas/{estatistica_id}/eliminar")
def eliminar_estatistica(estatistica_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_scouting)):
    registo = db.query(ScoutingEstatisticaJogo).filter(ScoutingEstatisticaJogo.id == estatistica_id).first()
    jogador = _jogador_acessivel(db, registo.jogador_id, utilizador) if registo else None
    if not jogador:
        return RedirectResponse(url="/scouting", status_code=303)
    db.delete(registo)
    db.commit()
    set_flash(request, "Registo estatístico eliminado.")
    return RedirectResponse(url=f"/scouting/jogadores/{jogador.id}#estatisticas", status_code=303)


@router.post("/jogadores/{jogador_id}/itens")
async def associar_item(jogador_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_scouting)):
    jogador = _jogador_acessivel(db, jogador_id, utilizador)
    if not jogador:
        return RedirectResponse(url="/scouting", status_code=303)
    dados = await request.form()
    categoria, nome = dados.get("categoria"), _limpo(dados.get("nome_novo"))
    item_id = _int(dados.get("item_id"))
    item = db.query(ScoutingItemBiblioteca).filter(ScoutingItemBiblioteca.id == item_id, ScoutingItemBiblioteca.clube_id == jogador.clube_id).first() if item_id else None
    if nome and categoria in CATEGORIAS_BIBLIOTECA:
        normalizado = _normalizar(nome)
        item = db.query(ScoutingItemBiblioteca).filter(ScoutingItemBiblioteca.clube_id == jogador.clube_id, ScoutingItemBiblioteca.categoria == categoria, ScoutingItemBiblioteca.nome_normalizado == normalizado).first()
        if not item:
            item = ScoutingItemBiblioteca(clube_id=jogador.clube_id, categoria=categoria, nome=nome, nome_normalizado=normalizado)
            db.add(item)
            db.flush()
    if not item:
        set_flash(request, "Seleciona uma opção da biblioteca ou cria uma nova.", "error")
    elif not db.query(ScoutingJogadorItem).filter(ScoutingJogadorItem.jogador_id == jogador.id, ScoutingJogadorItem.item_id == item.id).first():
        db.add(ScoutingJogadorItem(clube_id=jogador.clube_id, jogador_id=jogador.id, item_id=item.id, observacao=_limpo(dados.get("observacao"))))
        db.commit()
        set_flash(request, "Informação associada à ficha.")
    return RedirectResponse(url=f"/scouting/jogadores/{jogador.id}#leitura", status_code=303)


@router.post("/itens-associados/{associacao_id}/eliminar")
def remover_item(associacao_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_scouting)):
    associacao = db.query(ScoutingJogadorItem).filter(ScoutingJogadorItem.id == associacao_id).first()
    jogador = _jogador_acessivel(db, associacao.jogador_id, utilizador) if associacao else None
    if not jogador:
        return RedirectResponse(url="/scouting", status_code=303)
    db.delete(associacao)
    db.commit()
    return RedirectResponse(url=f"/scouting/jogadores/{jogador.id}#leitura", status_code=303)


@router.post("/itens-associados/{associacao_id}/guardar")
async def guardar_observacao_item(associacao_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_scouting)):
    associacao = db.query(ScoutingJogadorItem).filter(ScoutingJogadorItem.id == associacao_id).first()
    jogador = _jogador_acessivel(db, associacao.jogador_id, utilizador) if associacao else None
    if not jogador:
        return RedirectResponse(url="/scouting", status_code=303)
    dados = await request.form()
    associacao.observacao = _limpo(dados.get("observacao"))
    db.commit()
    set_flash(request, "Observação atualizada.")
    return RedirectResponse(url=f"/scouting/jogadores/{jogador.id}#leitura", status_code=303)


@router.post("/jogadores/{jogador_id}/zonas")
async def guardar_zonas(jogador_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_scouting)):
    jogador = _jogador_acessivel(db, jogador_id, utilizador)
    if not jogador:
        return RedirectResponse(url="/scouting", status_code=303)
    dados = await request.form()
    validas = {zona for zona, _ in ZONAS_CAMPO}
    selecionadas = [zona for zona in dados.getlist("zonas") if zona in validas]
    db.query(ScoutingZonaAcao).filter(ScoutingZonaAcao.jogador_id == jogador.id).delete(synchronize_session=False)
    for zona in selecionadas:
        db.add(ScoutingZonaAcao(clube_id=jogador.clube_id, jogador_id=jogador.id, zona=zona, observacao=_limpo(dados.get(f"observacao_{zona}"))))
    db.commit()
    set_flash(request, "Zonas de ação atualizadas.")
    return RedirectResponse(url=f"/scouting/jogadores/{jogador.id}#zonas", status_code=303)


@router.get("/jogos/{jogo_id}", response_class=HTMLResponse)
def pagina_scouting(
    jogo_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_scouting),
):
    jogo = db.query(Jogo).filter(Jogo.id == jogo_id).first()
    if not jogo:
        return RedirectResponse(url="/equipas", status_code=303)
    verificar_ou_negar_equipa(utilizador, jogo.equipa_id, db)
    _sincronizar_adversarios(db, utilizador)
    ligacao = db.query(ScoutingAdversarioJogo).filter(ScoutingAdversarioJogo.jogo_id == jogo.id).first()
    if ligacao:
        return RedirectResponse(url=f"/scouting/adversarios/{ligacao.adversario_id}/resumo", status_code=303)
    return RedirectResponse(url="/scouting", status_code=303)


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

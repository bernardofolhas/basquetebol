from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from template_config import Jinja2Templates
from sqlalchemy import or_
from sqlalchemy.orm import Session

from auth import verificar_acesso_equipa
from auth_deps import AcessoNegado, exigir_autenticacao
from database import get_db
from flash import set_flash
from models.equipa import Equipa
from models.playbook import (
    CadernoPlaybook,
    JogadaCadernoPlaybook,
    PassoSetPlay,
    Playbook,
    SecaoCadernoPlaybook,
    SetPlay,
)
from models.scouting import ScoutingConceitoOfensivo, ScoutingMomentoPlaybook
from services.desenho_service import (
    compor_desenho_sobre_campo,
    decompor_desenho_editavel,
    empacotar_desenho_editavel,
)
from services.imagem_playbook_service import preparar_imagem_passo
from services.importacao_ebp_service import (
    MAX_FICHEIRO_EBP_BYTES,
    interpretar_ebp,
    renderizar_sequencia_ebp,
)
from paths import STATIC_DIR, TEMPLATES_DIR
from services.pdf_service import content_disposition_pdf, renderizar_pdf

router = APIRouter(prefix="/playbook")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _redirect_playbook(url: str) -> RedirectResponse:
    """Mantém destinos editoriais intencionais apesar do retorno global à origem."""
    return RedirectResponse(
        url=url,
        status_code=303,
        headers={"x-context-redirect-locked": "1"},
    )


def _pedido_json(request: Request) -> bool:
    return (
        "application/json" in request.headers.get("accept", "")
        or request.headers.get("x-requested-with") == "XMLHttpRequest"
    )


def _serializar_passo(passo: PassoSetPlay) -> dict:
    desenho_imagem, desenho_estado = decompor_desenho_editavel(passo.desenho)
    return {
        "id": passo.id,
        "ordem": passo.ordem,
        "observacao": passo.observacao or "",
        "desenho": desenho_imagem,
        "estado": desenho_estado,
        "imagemCoach": passo.imagem_coach,
    }


def _verificar_acesso_playbook(utilizador, equipa_id: int | None, db: Session) -> None:
    if not equipa_id or not verificar_acesso_equipa(utilizador, equipa_id, db):
        raise AcessoNegado("/equipas")


def _equipa_id_por_playbook(db: Session, playbook_id: int) -> int | None:
    p = db.query(Playbook).filter(Playbook.id == playbook_id).first()
    return p.equipa_id if p else None


def _equipa_id_por_setplay(db: Session, setplay_id: int) -> int | None:
    s = db.query(SetPlay).filter(SetPlay.id == setplay_id).first()
    return _equipa_id_por_playbook(db, s.playbook_id) if s else None


def _equipa_id_por_passo(db: Session, passo_id: int) -> int | None:
    p = db.query(PassoSetPlay).filter(PassoSetPlay.id == passo_id).first()
    return _equipa_id_por_setplay(db, p.setplay_id) if p else None


def _equipa_id_por_caderno(db: Session, caderno_id: int) -> int | None:
    caderno = db.query(CadernoPlaybook).filter(CadernoPlaybook.id == caderno_id).first()
    return caderno.equipa_id if caderno else None


def _preparar_preview_setplay(setplay: SetPlay) -> None:
    primeiro = setplay.passos[0] if setplay.passos else None
    desenho = decompor_desenho_editavel(primeiro.desenho)[0] if primeiro and primeiro.desenho else None
    setplay.preview_imagem = (primeiro.imagem_coach if primeiro else None) or desenho


def _imagem_passo_para_pdf(passo: PassoSetPlay) -> str | None:
    desenho_imagem, estado = decompor_desenho_editavel(passo.desenho)
    tipo = estado.get("campoTipo") if isinstance(estado, dict) else None
    if tipo not in {"meio", "completo"} and isinstance(estado, dict):
        try:
            largura = float(estado.get("largura") or 0)
            altura = float(estado.get("altura") or 0)
        except (TypeError, ValueError):
            largura = altura = 0
        tipo = "completo" if largura and altura > largura else "meio"
    caminho = STATIC_DIR / "campos" / ("campo_completo.png" if tipo == "completo" else "campo_meio.png")
    return passo.imagem_coach or compor_desenho_sobre_campo(caminho, desenho_imagem)


def _normalizar_ordem_caderno(caderno: CadernoPlaybook, ignorar_id: int | None = None) -> None:
    grupos = [None] + [secao.id for secao in sorted(caderno.secoes, key=lambda item: (item.ordem, item.id))]
    for secao_id in grupos:
        entradas = sorted(
            [
                entrada for entrada in caderno.jogadas
                if entrada.secao_id == secao_id and entrada.id != ignorar_id
            ],
            key=lambda item: (item.ordem, item.id),
        )
        for ordem, entrada in enumerate(entradas):
            entrada.ordem = ordem


# ── PLAYBOOK DE UMA EQUIPA ────────────────────────────────────────────────────
@router.get("/equipas/{equipa_id}", response_class=HTMLResponse)
def playbook_equipa(equipa_id: int, request: Request, db: Session = Depends(get_db),
                    utilizador=Depends(exigir_autenticacao)):
    _verificar_acesso_playbook(utilizador, equipa_id, db)
    equipa = db.query(Equipa).filter(Equipa.id == equipa_id).first()
    if not equipa:
        return RedirectResponse(url="/equipas")

    playbook = db.query(Playbook).filter(Playbook.equipa_id == equipa_id).first()
    if not playbook:
        playbook = Playbook(
            clube_id=equipa.clube_id,
            equipa_id=equipa_id,
            nome=f"Playbook — {equipa.nome}",
        )
        db.add(playbook)
        db.commit()
        db.refresh(playbook)

    categorias = ["Ataque", "Defesa", "Transição Ofensiva", "Transição Defensiva", "Zona", "Bola Parada", "Outro"]
    for setplay in playbook.setplays:
        _preparar_preview_setplay(setplay)
    cadernos = (
        db.query(CadernoPlaybook)
        .filter(CadernoPlaybook.equipa_id == equipa_id)
        .order_by(CadernoPlaybook.ordem, CadernoPlaybook.id)
        .all()
    )
    return templates.TemplateResponse(request, "playbook/lista.html", {
        "utilizador": utilizador,
        "equipa": equipa,
        "playbook": playbook,
        "setplays": playbook.setplays,
        "cadernos": cadernos,
        "categorias": categorias,
    })


@router.post("/equipas/{equipa_id}/cadernos/novo")
async def criar_caderno_playbook(
    equipa_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
    nome: str = Form(...),
    descricao: str = Form(""),
):
    _verificar_acesso_playbook(utilizador, equipa_id, db)
    equipa = db.query(Equipa).filter(Equipa.id == equipa_id).first()
    if not equipa:
        return RedirectResponse(url="/equipas", status_code=303)
    total = db.query(CadernoPlaybook).filter(CadernoPlaybook.equipa_id == equipa_id).count()
    caderno = CadernoPlaybook(
        clube_id=equipa.clube_id,
        equipa_id=equipa_id,
        nome=nome.strip() or "Novo playbook",
        descricao=descricao.strip() or None,
        ordem=total,
    )
    db.add(caderno)
    db.commit()
    db.refresh(caderno)
    set_flash(request, f"Playbook '{caderno.nome}' criado.")
    return _redirect_playbook(f"/playbook/cadernos/{caderno.id}")


@router.get("/cadernos/{caderno_id}", response_class=HTMLResponse)
def detalhe_caderno_playbook(
    caderno_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    equipa_id = _equipa_id_por_caderno(db, caderno_id)
    _verificar_acesso_playbook(utilizador, equipa_id, db)
    caderno = db.query(CadernoPlaybook).filter(CadernoPlaybook.id == caderno_id).first()
    if not caderno:
        return RedirectResponse(url="/equipas", status_code=303)
    biblioteca = db.query(Playbook).filter(Playbook.equipa_id == caderno.equipa_id).first()
    setplays = list(biblioteca.setplays) if biblioteca else []
    for setplay in setplays:
        _preparar_preview_setplay(setplay)
    for entrada in caderno.jogadas:
        _preparar_preview_setplay(entrada.setplay)
    sem_secao = sorted(
        [entrada for entrada in caderno.jogadas if entrada.secao_id is None],
        key=lambda item: (item.ordem, item.id),
    )
    return templates.TemplateResponse(request, "playbook/caderno.html", {
        "utilizador": utilizador,
        "equipa": caderno.equipa,
        "caderno": caderno,
        "secoes": sorted(caderno.secoes, key=lambda item: (item.ordem, item.id)),
        "sem_secao": sem_secao,
        "setplays": setplays,
    })


@router.post("/cadernos/{caderno_id}/editar")
async def editar_caderno_playbook(
    caderno_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
    nome: str = Form(...),
    descricao: str = Form(""),
):
    equipa_id = _equipa_id_por_caderno(db, caderno_id)
    _verificar_acesso_playbook(utilizador, equipa_id, db)
    caderno = db.query(CadernoPlaybook).filter(CadernoPlaybook.id == caderno_id).first()
    if caderno:
        caderno.nome = nome.strip() or caderno.nome
        caderno.descricao = descricao.strip() or None
        db.commit()
    return RedirectResponse(url=f"/playbook/cadernos/{caderno_id}", status_code=303)


@router.post("/cadernos/{caderno_id}/secoes/novo")
async def criar_secao_caderno(
    caderno_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
    nome: str = Form(...),
):
    equipa_id = _equipa_id_por_caderno(db, caderno_id)
    _verificar_acesso_playbook(utilizador, equipa_id, db)
    caderno = db.query(CadernoPlaybook).filter(CadernoPlaybook.id == caderno_id).first()
    if caderno:
        db.add(SecaoCadernoPlaybook(
            clube_id=caderno.clube_id,
            caderno_id=caderno.id,
            nome=nome.strip() or "Nova secção",
            ordem=len(caderno.secoes),
        ))
        db.commit()
    return RedirectResponse(url=f"/playbook/cadernos/{caderno_id}", status_code=303)


@router.post("/cadernos/{caderno_id}/jogadas/adicionar")
async def adicionar_jogadas_caderno(
    caderno_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
    setplay_ids: list[int] = Form(default=[]),
    secao_id: int | None = Form(default=None),
):
    equipa_id = _equipa_id_por_caderno(db, caderno_id)
    _verificar_acesso_playbook(utilizador, equipa_id, db)
    caderno = db.query(CadernoPlaybook).filter(CadernoPlaybook.id == caderno_id).first()
    if not caderno:
        return RedirectResponse(url="/equipas", status_code=303)
    if secao_id and not any(secao.id == secao_id for secao in caderno.secoes):
        secao_id = None
    ids_existentes = {entrada.setplay_id for entrada in caderno.jogadas}
    validos = (
        db.query(SetPlay)
        .join(Playbook)
        .filter(SetPlay.id.in_(setplay_ids), Playbook.equipa_id == caderno.equipa_id)
        .all()
        if setplay_ids else []
    )
    ordem = len([entrada for entrada in caderno.jogadas if entrada.secao_id == secao_id])
    for setplay in validos:
        if setplay.id in ids_existentes:
            continue
        db.add(JogadaCadernoPlaybook(
            clube_id=caderno.clube_id,
            caderno_id=caderno.id,
            secao_id=secao_id,
            setplay_id=setplay.id,
            ordem=ordem,
        ))
        ordem += 1
    db.commit()
    return RedirectResponse(url=f"/playbook/cadernos/{caderno_id}", status_code=303)


@router.post("/cadernos/{caderno_id}/reordenar")
async def reordenar_jogadas_caderno(
    caderno_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    equipa_id = _equipa_id_por_caderno(db, caderno_id)
    _verificar_acesso_playbook(utilizador, equipa_id, db)
    caderno = db.query(CadernoPlaybook).filter(CadernoPlaybook.id == caderno_id).first()
    if not caderno:
        return JSONResponse({"sucesso": False, "erro": "Playbook não encontrado."}, status_code=404)
    dados = await request.json()
    grupos = dados.get("grupos") or []
    ids_recebidos = [int(item) for grupo in grupos for item in (grupo.get("jogada_ids") or [])]
    entradas = {entrada.id: entrada for entrada in caderno.jogadas}
    if len(ids_recebidos) != len(set(ids_recebidos)) or set(ids_recebidos) != set(entradas):
        return JSONResponse({"sucesso": False, "erro": "A sequência recebida está incompleta."}, status_code=422)
    secoes_validas = {secao.id for secao in caderno.secoes}
    for grupo in grupos:
        secao_id = grupo.get("secao_id")
        secao_id = int(secao_id) if secao_id not in (None, "") else None
        if secao_id is not None and secao_id not in secoes_validas:
            return JSONResponse({"sucesso": False, "erro": "Secção inválida."}, status_code=422)
        for ordem, entrada_id in enumerate(grupo.get("jogada_ids") or []):
            entrada = entradas[int(entrada_id)]
            entrada.secao_id = secao_id
            entrada.ordem = ordem
    db.commit()
    return JSONResponse({"sucesso": True})


@router.post("/cadernos/jogadas/{entrada_id}/eliminar")
async def eliminar_jogada_caderno(
    entrada_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    entrada = db.query(JogadaCadernoPlaybook).filter(JogadaCadernoPlaybook.id == entrada_id).first()
    equipa_id = _equipa_id_por_caderno(db, entrada.caderno_id) if entrada else None
    _verificar_acesso_playbook(utilizador, equipa_id, db)
    if not entrada:
        return RedirectResponse(url="/equipas", status_code=303)
    caderno = entrada.caderno
    caderno_id = caderno.id
    db.delete(entrada)
    db.flush()
    _normalizar_ordem_caderno(caderno, ignorar_id=entrada_id)
    db.commit()
    return RedirectResponse(url=f"/playbook/cadernos/{caderno_id}", status_code=303)


@router.post("/cadernos/secoes/{secao_id}/eliminar")
async def eliminar_secao_caderno(
    secao_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    secao = db.query(SecaoCadernoPlaybook).filter(SecaoCadernoPlaybook.id == secao_id).first()
    equipa_id = _equipa_id_por_caderno(db, secao.caderno_id) if secao else None
    _verificar_acesso_playbook(utilizador, equipa_id, db)
    if not secao:
        return RedirectResponse(url="/equipas", status_code=303)
    caderno = secao.caderno
    caderno_id = caderno.id
    for entrada in list(secao.jogadas):
        entrada.secao_id = None
    db.delete(secao)
    db.flush()
    _normalizar_ordem_caderno(caderno)
    db.commit()
    return RedirectResponse(url=f"/playbook/cadernos/{caderno_id}", status_code=303)


@router.post("/cadernos/{caderno_id}/eliminar")
async def eliminar_caderno_playbook(
    caderno_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    equipa_id = _equipa_id_por_caderno(db, caderno_id)
    _verificar_acesso_playbook(utilizador, equipa_id, db)
    caderno = db.query(CadernoPlaybook).filter(CadernoPlaybook.id == caderno_id).first()
    if caderno:
        db.delete(caderno)
        db.commit()
    return _redirect_playbook(f"/playbook/equipas/{equipa_id}#cadernos")


# ── CRIAR SETPLAY ────────────────────────────────────────────────────────────
@router.post("/equipas/{equipa_id}/setplays/novo")
async def criar_setplay(equipa_id: int, request: Request, db: Session = Depends(get_db),
                        utilizador=Depends(exigir_autenticacao),
                        nome: str = Form(...),
                        categoria: str = Form(""),
                        descricao: str = Form("")):
    _verificar_acesso_playbook(utilizador, equipa_id, db)
    playbook = db.query(Playbook).filter(Playbook.equipa_id == equipa_id).first()
    if not playbook:
        return RedirectResponse(url=f"/playbook/equipas/{equipa_id}", status_code=303)

    ordem = len(playbook.setplays)
    setplay = SetPlay(
        clube_id=playbook.clube_id,
        playbook_id=playbook.id,
        nome=nome,
        categoria=categoria or None,
        descricao=descricao or None,
        ordem=ordem,
    )
    db.add(setplay)
    db.flush()
    db.add(PassoSetPlay(
        clube_id=playbook.clube_id,
        setplay_id=setplay.id,
        ordem=0,
    ))
    db.commit()
    db.refresh(setplay)
    set_flash(request, f"Setplay '{nome}' criado.")
    return _redirect_playbook(f"/playbook/studio/setplays/{setplay.id}")


@router.post("/equipas/{equipa_id}/setplays/importar-ebp")
async def importar_setplay_ebp(
    equipa_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
    ficheiro: UploadFile = File(...),
    categoria: str = Form(""),
):
    _verificar_acesso_playbook(utilizador, equipa_id, db)
    equipa = db.query(Equipa).filter(Equipa.id == equipa_id).first()
    if not equipa:
        return RedirectResponse(url="/equipas", status_code=303)

    try:
        conteudo = await ficheiro.read(MAX_FICHEIRO_EBP_BYTES + 1)
        jogada = interpretar_ebp(conteudo)
        imagens = [renderizar_sequencia_ebp(sequencia) for sequencia in jogada.sequencias]
    except ValueError as erro:
        set_flash(request, str(erro), tipo="error")
        return RedirectResponse(url=f"/playbook/equipas/{equipa_id}", status_code=303)

    playbook = db.query(Playbook).filter(Playbook.equipa_id == equipa_id).first()
    if not playbook:
        playbook = Playbook(
            clube_id=equipa.clube_id,
            equipa_id=equipa_id,
            nome=f"Playbook — {equipa.nome}",
        )
        db.add(playbook)
        db.flush()

    setplay = (
        db.query(SetPlay)
        .filter(
            SetPlay.playbook_id == playbook.id,
            SetPlay.nome == jogada.nome,
            or_(SetPlay.origem == "ebp", SetPlay.descricao.like("Categoria de origem:%")),
        )
        .order_by(SetPlay.id.desc())
        .first()
    )
    atualizacao = setplay is not None
    if setplay:
        setplay.origem = "ebp"
        setplay.categoria = categoria or setplay.categoria or "Outro"
        if not setplay.descricao:
            setplay.descricao = jogada.descricao or None
    else:
        setplay = SetPlay(
            clube_id=playbook.clube_id,
            playbook_id=playbook.id,
            nome=jogada.nome,
            categoria=categoria or "Outro",
            descricao=jogada.descricao or None,
            origem="ebp",
            ordem=len(playbook.setplays),
        )
        db.add(setplay)
        db.flush()

    passos_existentes = {passo.ordem: passo for passo in setplay.passos}
    for ordem, (sequencia, imagem) in enumerate(zip(jogada.sequencias, imagens)):
        passo = passos_existentes.get(ordem)
        if passo:
            passo.imagem_coach = imagem
            if not passo.observacao:
                passo.observacao = sequencia.texto or None
        else:
            db.add(PassoSetPlay(
                clube_id=playbook.clube_id,
                setplay_id=setplay.id,
                ordem=ordem,
                observacao=sequencia.texto or None,
                imagem_coach=imagem,
            ))
    db.commit()
    acao = "atualizada" if atualizacao else "importada"
    set_flash(request, f"'{jogada.nome}' {acao} com {len(imagens)} passos editáveis.")
    return _redirect_playbook(f"/playbook/studio/setplays/{setplay.id}")


# ── DETALHE / EDITOR DE SETPLAY ───────────────────────────────────────────────
@router.get("/setplays/{setplay_id}", response_class=HTMLResponse)
def detalhe_setplay(setplay_id: int, request: Request, db: Session = Depends(get_db),
                    utilizador=Depends(exigir_autenticacao)):
    equipa_id = _equipa_id_por_setplay(db, setplay_id)
    _verificar_acesso_playbook(utilizador, equipa_id, db)
    return _redirect_playbook(f"/playbook/studio/setplays/{setplay_id}")


@router.get("/studio/setplays/{setplay_id}", response_class=HTMLResponse)
def studio_setplay(setplay_id: int, request: Request, db: Session = Depends(get_db),
                   utilizador=Depends(exigir_autenticacao)):
    equipa_id = _equipa_id_por_setplay(db, setplay_id)
    _verificar_acesso_playbook(utilizador, equipa_id, db)

    setplay = db.query(SetPlay).filter(SetPlay.id == setplay_id).first()
    if not setplay:
        return RedirectResponse(url="/equipas")

    for passo in setplay.passos:
        passo.desenho_imagem, passo.desenho_estado = decompor_desenho_editavel(passo.desenho)

    categorias = ["Ataque", "Defesa", "Transição Ofensiva", "Transição Defensiva", "Zona", "Bola Parada", "Outro"]
    elemento_scouting = db.query(ScoutingConceitoOfensivo).filter(ScoutingConceitoOfensivo.setplay_id == setplay.id).first()
    ancora_scouting = "#conceitos"
    if not elemento_scouting:
        elemento_scouting = db.query(ScoutingMomentoPlaybook).filter(ScoutingMomentoPlaybook.setplay_id == setplay.id).first()
        ancora_scouting = "#playbook-coletivo"
    url_voltar = (
        f"/scouting/adversarios/{elemento_scouting.adversario_id}/coletivo{ancora_scouting}"
        if elemento_scouting else f"/playbook/equipas/{setplay.playbook.equipa_id}"
    )
    return templates.TemplateResponse(request, "playbook/detalhe.html", {
        "utilizador": utilizador,
        "setplay": setplay,
        "playbook": setplay.playbook,
        "equipa": setplay.playbook.equipa,
        "passos": setplay.passos,
        "passos_studio": [_serializar_passo(passo) for passo in setplay.passos],
        "categorias": categorias,
        "url_voltar": url_voltar,
    })


# ── EDITAR SETPLAY ────────────────────────────────────────────────────────────
@router.post("/setplays/{setplay_id}/editar")
async def editar_setplay(setplay_id: int, request: Request, db: Session = Depends(get_db),
                         utilizador=Depends(exigir_autenticacao),
                         nome: str = Form(...),
                         categoria: str = Form(""),
                         descricao: str = Form("")):
    equipa_id = _equipa_id_por_setplay(db, setplay_id)
    _verificar_acesso_playbook(utilizador, equipa_id, db)
    setplay = db.query(SetPlay).filter(SetPlay.id == setplay_id).first()
    if setplay:
        setplay.nome = nome
        setplay.categoria = categoria or None
        setplay.descricao = descricao or None
        db.commit()
        set_flash(request, "Setplay atualizado.")
    return RedirectResponse(url=f"/playbook/studio/setplays/{setplay_id}", status_code=303)


@router.post("/setplays/{setplay_id}/editar-json")
async def editar_setplay_json(
    setplay_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    equipa_id = _equipa_id_por_setplay(db, setplay_id)
    _verificar_acesso_playbook(utilizador, equipa_id, db)
    setplay = db.query(SetPlay).filter(SetPlay.id == setplay_id).first()
    if not setplay:
        return JSONResponse({"sucesso": False, "erro": "Jogada não encontrada."}, status_code=404)
    dados = await request.json()
    nome = str(dados.get("nome") or "").strip()
    if not nome:
        return JSONResponse({"sucesso": False, "erro": "O título é obrigatório."}, status_code=422)
    setplay.nome = nome
    setplay.categoria = str(dados.get("categoria") or "").strip() or None
    setplay.descricao = str(dados.get("descricao") or "").strip() or None
    db.commit()
    return JSONResponse({
        "sucesso": True,
        "setplay": {
            "id": setplay.id,
            "nome": setplay.nome,
            "categoria": setplay.categoria or "",
            "descricao": setplay.descricao or "",
        },
    })


# ── ELIMINAR SETPLAY ───────────────────────────────────────────────────────────
@router.post("/setplays/{setplay_id}/eliminar")
async def eliminar_setplay(setplay_id: int, request: Request, db: Session = Depends(get_db),
                           utilizador=Depends(exigir_autenticacao)):
    equipa_id = _equipa_id_por_setplay(db, setplay_id)
    _verificar_acesso_playbook(utilizador, equipa_id, db)
    setplay = db.query(SetPlay).filter(SetPlay.id == setplay_id).first()
    if setplay:
        playbook_id = setplay.playbook_id
        equipa_id_redirect = equipa_id
        db.delete(setplay)
        db.commit()
        set_flash(request, "Setplay eliminado.")
        return _redirect_playbook(f"/playbook/equipas/{equipa_id_redirect}")
    return RedirectResponse(url="/equipas", status_code=303)


# ── ADICIONAR PASSO ────────────────────────────────────────────────────────────
@router.post("/setplays/{setplay_id}/passos/novo")
async def adicionar_passo(setplay_id: int, request: Request, db: Session = Depends(get_db),
                          utilizador=Depends(exigir_autenticacao)):
    equipa_id = _equipa_id_por_setplay(db, setplay_id)
    _verificar_acesso_playbook(utilizador, equipa_id, db)
    setplay = db.query(SetPlay).filter(SetPlay.id == setplay_id).first()
    if setplay:
        ordem = len(setplay.passos)
        passo = PassoSetPlay(
            clube_id=setplay.clube_id,
            setplay_id=setplay_id,
            ordem=ordem,
        )
        db.add(passo)
        db.commit()
        db.refresh(passo)
        if _pedido_json(request):
            return JSONResponse({"sucesso": True, "passo": _serializar_passo(passo)})
    elif _pedido_json(request):
        return JSONResponse({"sucesso": False, "erro": "Jogada não encontrada."}, status_code=404)
    return RedirectResponse(url=f"/playbook/studio/setplays/{setplay_id}", status_code=303)


@router.post("/passos/{passo_id}/duplicar")
async def duplicar_passo(
    passo_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    equipa_id = _equipa_id_por_passo(db, passo_id)
    _verificar_acesso_playbook(utilizador, equipa_id, db)
    passo = db.query(PassoSetPlay).filter(PassoSetPlay.id == passo_id).first()
    if not passo:
        if _pedido_json(request):
            return JSONResponse({"sucesso": False, "erro": "Cena não encontrada."}, status_code=404)
        return RedirectResponse(url="/equipas", status_code=303)

    seguintes = (
        db.query(PassoSetPlay)
        .filter(PassoSetPlay.setplay_id == passo.setplay_id, PassoSetPlay.ordem > passo.ordem)
        .order_by(PassoSetPlay.ordem.desc())
        .all()
    )
    for seguinte in seguintes:
        seguinte.ordem += 1
    copia = PassoSetPlay(
        clube_id=passo.clube_id,
        setplay_id=passo.setplay_id,
        ordem=passo.ordem + 1,
        observacao=passo.observacao,
        desenho=passo.desenho,
        imagem_coach=passo.imagem_coach,
    )
    db.add(copia)
    db.commit()
    db.refresh(copia)
    if _pedido_json(request):
        return JSONResponse({"sucesso": True, "passo": _serializar_passo(copia)})
    return RedirectResponse(url=f"/playbook/studio/setplays/{passo.setplay_id}", status_code=303)


@router.post("/setplays/{setplay_id}/passos/reordenar")
async def reordenar_passos_setplay(
    setplay_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    equipa_id = _equipa_id_por_setplay(db, setplay_id)
    _verificar_acesso_playbook(utilizador, equipa_id, db)
    passos = db.query(PassoSetPlay).filter(PassoSetPlay.setplay_id == setplay_id).all()
    dados = await request.json()
    ids = [int(item) for item in (dados.get("passo_ids") or [])]
    mapa = {passo.id: passo for passo in passos}
    if len(ids) != len(set(ids)) or set(ids) != set(mapa):
        return JSONResponse({"sucesso": False, "erro": "A sequência recebida está incompleta."}, status_code=422)
    for ordem, passo_id in enumerate(ids):
        mapa[passo_id].ordem = ordem
    db.commit()
    return JSONResponse({"sucesso": True})


# ── ELIMINAR PASSO ─────────────────────────────────────────────────────────────
@router.post("/passos/{passo_id}/eliminar")
async def eliminar_passo(passo_id: int, request: Request, db: Session = Depends(get_db),
                         utilizador=Depends(exigir_autenticacao)):
    equipa_id = _equipa_id_por_passo(db, passo_id)
    _verificar_acesso_playbook(utilizador, equipa_id, db)
    passo = db.query(PassoSetPlay).filter(PassoSetPlay.id == passo_id).first()
    if passo:
        setplay_id = passo.setplay_id
        db.delete(passo)
        db.commit()
        # Re-number remaining steps
        restantes = db.query(PassoSetPlay).filter(
            PassoSetPlay.setplay_id == setplay_id
        ).order_by(PassoSetPlay.ordem).all()
        for i, p in enumerate(restantes):
            p.ordem = i
        db.commit()
        if _pedido_json(request):
            return JSONResponse({"sucesso": True, "passo_ids": [p.id for p in restantes]})
        set_flash(request, "Passo eliminado.")
        return RedirectResponse(url=f"/playbook/studio/setplays/{setplay_id}", status_code=303)
    if _pedido_json(request):
        return JSONResponse({"sucesso": False, "erro": "Cena não encontrada."}, status_code=404)
    return RedirectResponse(url="/equipas", status_code=303)


# ── GUARDAR OBSERVAÇÃO DO PASSO (form POST) ────────────────────────────────────
@router.post("/passos/{passo_id}/observacao")
async def guardar_observacao_passo(passo_id: int, request: Request, db: Session = Depends(get_db),
                                   utilizador=Depends(exigir_autenticacao),
                                   observacao: str = Form("")):
    equipa_id = _equipa_id_por_passo(db, passo_id)
    _verificar_acesso_playbook(utilizador, equipa_id, db)
    passo = db.query(PassoSetPlay).filter(PassoSetPlay.id == passo_id).first()
    if passo:
        passo.observacao = observacao or None
        db.commit()
    return RedirectResponse(url=f"/playbook/studio/setplays/{passo.setplay_id}", status_code=303)


@router.post("/passos/{passo_id}/observacao-json")
async def guardar_observacao_passo_json(
    passo_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    equipa_id = _equipa_id_por_passo(db, passo_id)
    _verificar_acesso_playbook(utilizador, equipa_id, db)
    passo = db.query(PassoSetPlay).filter(PassoSetPlay.id == passo_id).first()
    if not passo:
        return JSONResponse({"sucesso": False, "erro": "Cena não encontrada."}, status_code=404)
    dados = await request.json()
    passo.observacao = str(dados.get("observacao") or "").strip() or None
    db.commit()
    return JSONResponse({"sucesso": True, "observacao": passo.observacao or ""})


# ── GUARDAR DESENHO DO PASSO (AJAX JSON) ──────────────────────────────────────
@router.post("/passos/{passo_id}/desenho")
async def guardar_desenho_passo(passo_id: int, request: Request, db: Session = Depends(get_db),
                                utilizador=Depends(exigir_autenticacao)):
    from fastapi.responses import JSONResponse
    try:
        equipa_id = _equipa_id_por_passo(db, passo_id)
        _verificar_acesso_playbook(utilizador, equipa_id, db)
        body = await request.json()
        dados = empacotar_desenho_editavel(body.get("dados"), body.get("estado"))
        passo = db.query(PassoSetPlay).filter(PassoSetPlay.id == passo_id).first()
        if not passo:
            return JSONResponse({"sucesso": False, "erro": "Passo não encontrado"})
        if not dados:
            return JSONResponse({"sucesso": False, "erro": "O desenho enviado não é uma imagem válida."}, status_code=400)
        passo.desenho = dados
        db.commit()
        return JSONResponse({"sucesso": True})
    except Exception as exc:
        return JSONResponse({"sucesso": False, "erro": str(exc)})


@router.post("/passos/{passo_id}/imagem")
async def guardar_imagem_passo(
    passo_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
    imagem: UploadFile = File(...),
):
    equipa_id = _equipa_id_por_passo(db, passo_id)
    _verificar_acesso_playbook(utilizador, equipa_id, db)
    passo = db.query(PassoSetPlay).filter(PassoSetPlay.id == passo_id).first()
    if not passo:
        return RedirectResponse(url="/equipas", status_code=303)
    try:
        passo.imagem_coach = preparar_imagem_passo(await imagem.read())
        db.commit()
        set_flash(request, "Imagem adicionada ao passo.")
    except ValueError as erro:
        set_flash(request, str(erro), tipo="error")
    return RedirectResponse(url=f"/playbook/studio/setplays/{passo.setplay_id}", status_code=303)


@router.post("/passos/{passo_id}/imagem/eliminar")
async def eliminar_imagem_passo(
    passo_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    equipa_id = _equipa_id_por_passo(db, passo_id)
    _verificar_acesso_playbook(utilizador, equipa_id, db)
    passo = db.query(PassoSetPlay).filter(PassoSetPlay.id == passo_id).first()
    if not passo:
        return RedirectResponse(url="/equipas", status_code=303)
    passo.imagem_coach = None
    db.commit()
    set_flash(request, "Imagem removida. O desenho tático mantém-se disponível.")
    return RedirectResponse(url=f"/playbook/studio/setplays/{passo.setplay_id}", status_code=303)


# ── MOVER PASSO PARA CIMA/BAIXO ───────────────────────────────────────────────
@router.post("/passos/{passo_id}/mover/{direcao}")
async def mover_passo(passo_id: int, direcao: str, request: Request,
                      db: Session = Depends(get_db), utilizador=Depends(exigir_autenticacao)):
    equipa_id = _equipa_id_por_passo(db, passo_id)
    _verificar_acesso_playbook(utilizador, equipa_id, db)
    passo = db.query(PassoSetPlay).filter(PassoSetPlay.id == passo_id).first()
    if not passo:
        return RedirectResponse(url="/equipas", status_code=303)

    passos = db.query(PassoSetPlay).filter(
        PassoSetPlay.setplay_id == passo.setplay_id
    ).order_by(PassoSetPlay.ordem).all()

    idx = next((i for i, p in enumerate(passos) if p.id == passo_id), None)
    if idx is None:
        return RedirectResponse(url=f"/playbook/studio/setplays/{passo.setplay_id}", status_code=303)

    swap_idx = idx - 1 if direcao == "cima" else idx + 1
    if 0 <= swap_idx < len(passos):
        passos[idx].ordem, passos[swap_idx].ordem = passos[swap_idx].ordem, passos[idx].ordem
        db.commit()

    return RedirectResponse(url=f"/playbook/studio/setplays/{passo.setplay_id}", status_code=303)


# ── EXPORTAR SETPLAY EM PDF ────────────────────────────────────────────────────
@router.get("/cadernos/{caderno_id}/pdf")
def exportar_pdf_caderno(
    caderno_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    equipa_id = _equipa_id_por_caderno(db, caderno_id)
    _verificar_acesso_playbook(utilizador, equipa_id, db)
    caderno = db.query(CadernoPlaybook).filter(CadernoPlaybook.id == caderno_id).first()
    if not caderno:
        return RedirectResponse(url="/equipas")

    for entrada in caderno.jogadas:
        for passo in entrada.setplay.passos:
            passo.imagem_composta_pdf = _imagem_passo_para_pdf(passo)

    grupos = [{"nome": "Sem secção", "jogadas": [entrada for entrada in caderno.jogadas if entrada.secao_id is None]}]
    grupos.extend({"nome": secao.nome, "jogadas": list(secao.jogadas)} for secao in caderno.secoes)
    pdf_bytes = renderizar_pdf(request, "playbook/caderno_pdf.html", {
        "caderno": caderno,
        "equipa": caderno.equipa,
        "grupos": [grupo for grupo in grupos if grupo["jogadas"]],
    })
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": content_disposition_pdf(f"Playbook {caderno.nome}")},
    )


@router.get("/setplays/{setplay_id}/pdf")
def exportar_pdf_setplay(setplay_id: int, request: Request, db: Session = Depends(get_db),
                         utilizador=Depends(exigir_autenticacao)):
    equipa_id = _equipa_id_por_setplay(db, setplay_id)
    _verificar_acesso_playbook(utilizador, equipa_id, db)
    setplay = db.query(SetPlay).filter(SetPlay.id == setplay_id).first()
    if not setplay:
        return RedirectResponse(url="/equipas")

    for passo in setplay.passos:
        passo.imagem_composta_pdf = _imagem_passo_para_pdf(passo)

    pdf_bytes = renderizar_pdf(request, "playbook/pdf.html", {
        "setplay": setplay,
        "equipa": setplay.playbook.equipa,
        "passos": setplay.passos,
    })
    return Response(content=pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": content_disposition_pdf(f"Jogada {setplay.nome}")})

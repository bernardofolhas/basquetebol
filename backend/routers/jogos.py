from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from template_config import Jinja2Templates
from sqlalchemy.orm import Session

from auth import verificar_perfil
from auth_deps import exigir_autenticacao, verificar_ou_negar_equipa
from database import get_db
from flash import set_flash
from models.equipa import Equipa
from models.jogador import Jogador
from models.jogo import Convocado, Jogo, PlanoJogo
from paths import TEMPLATES_DIR
from services.notificacoes_service import criar_notificacoes_para_equipa
from services.pdf_service import renderizar_pdf
from services.jogos_service import formatar_confronto, preparar_linhas_calendario_jogos

router = APIRouter(prefix="/jogos")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _obter_jogo(db: Session, jogo_id: int):
    return db.query(Jogo).filter(Jogo.id == jogo_id).first()


def _atualizar_campos_jogo(jogo: Jogo, data: str, hora: str, local: str,
                            adversario: str, competicao: str, em_casa: str, observacoes: str) -> None:
    jogo.data = date.fromisoformat(data)
    jogo.hora = hora or None
    jogo.local = local or None
    jogo.adversario = adversario
    jogo.competicao = competicao or None
    jogo.em_casa = em_casa == "true"
    jogo.observacoes = observacoes or None


def _mensagem_novo_jogo(jogo: Jogo) -> str:
    """Resumo curto e útil para a caixa de notificações do treinador."""
    detalhes = [jogo.data.strftime("%d/%m/%Y")]
    if jogo.hora:
        detalhes.append(jogo.hora)
    if jogo.local:
        detalhes.append(jogo.local)
    localidade = "em casa" if jogo.em_casa else "fora"
    return f"{jogo.adversario} · {localidade} · " + " · ".join(detalhes)


def _nome_clube_pedido(request: Request, equipa: Equipa) -> str:
    identidade = getattr(request.state, "identidade_clube", {}) or {}
    return identidade.get("nome_curto") or identidade.get("nome_oficial") or equipa.nome


def _confrontos(jogos: list[Jogo], nome_clube: str) -> dict[int, str]:
    return {
        jogo.id: formatar_confronto(nome_clube, jogo.adversario, jogo.em_casa)
        for jogo in jogos
    }


@router.get("/equipas/{equipa_id}", response_class=HTMLResponse)
def calendario_jogos(
    equipa_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    verificar_ou_negar_equipa(utilizador, equipa_id, db)

    equipa = db.query(Equipa).filter(Equipa.id == equipa_id).first()
    if not equipa:
        return RedirectResponse(url="/equipas")

    jogos = db.query(Jogo).filter(Jogo.equipa_id == equipa_id).order_by(Jogo.data).all()
    nome_clube = _nome_clube_pedido(request, equipa)

    return templates.TemplateResponse(request, "jogos/calendario.html", {
        "utilizador": utilizador,
        "equipa": equipa,
        "jogos": jogos,
        "confrontos": _confrontos(jogos, nome_clube),
        "linhas_jogos": preparar_linhas_calendario_jogos(jogos, nome_clube),
    })


@router.get("/equipas/{equipa_id}/pdf")
def exportar_pdf_calendario_equipa(
    equipa_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    verificar_ou_negar_equipa(utilizador, equipa_id, db)
    equipa = db.query(Equipa).filter(Equipa.id == equipa_id).first()
    if not equipa:
        return RedirectResponse(url="/equipas")
    jogos = db.query(Jogo).filter(Jogo.equipa_id == equipa_id).order_by(Jogo.data, Jogo.hora).all()
    nome_clube = _nome_clube_pedido(request, equipa)
    pdf_bytes = renderizar_pdf(request, "jogos/calendario_pdf.html", {
        "utilizador": utilizador,
        "equipa": equipa,
        "jogos": jogos,
        "confrontos": _confrontos(jogos, nome_clube),
        "linhas_jogos": preparar_linhas_calendario_jogos(jogos, nome_clube),
        "hoje": date.today(),
    })
    nome = f"calendario_{equipa.nome}_{equipa.id}.pdf".replace(" ", "_")
    return Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={nome}"})


@router.post("/equipas/{equipa_id}/novo")
async def criar_jogo(
    equipa_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
    data: str = Form(...),
    hora: str = Form(""),
    local: str = Form(""),
    adversario: str = Form(...),
    competicao: str = Form(""),
    em_casa: str = Form("true"),
    observacoes: str = Form(""),
):
    verificar_ou_negar_equipa(utilizador, equipa_id, db)

    jogo = Jogo(
        data=date.fromisoformat(data),
        hora=hora or None,
        local=local or None,
        adversario=adversario,
        competicao=competicao or None,
        em_casa=em_casa == "true",
        observacoes=observacoes or None,
        equipa_id=equipa_id,
    )
    db.add(jogo)
    db.flush()

    if verificar_perfil(utilizador, ["administrador", "coordenador"]):
        equipa = db.query(Equipa).filter(Equipa.id == equipa_id).first()
        if equipa:
            criar_notificacoes_para_equipa(
                db,
                equipa,
                "Jogo marcado",
                _mensagem_novo_jogo(jogo),
                f"/jogos/{jogo.id}",
            )
    db.commit()
    set_flash(request, f"Jogo contra '{adversario}' criado.")
    return RedirectResponse(url=f"/jogos/equipas/{equipa_id}", status_code=303)


@router.get("/{jogo_id}", response_class=HTMLResponse)
def detalhe_jogo(
    jogo_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    jogo = _obter_jogo(db, jogo_id)
    if not jogo:
        return RedirectResponse(url="/equipas")
    verificar_ou_negar_equipa(utilizador, jogo.equipa_id, db)

    jogadores = db.query(Jogador).filter(
        Jogador.equipa_id == jogo.equipa_id
    ).order_by(Jogador.nome).all()
    convocados_ids = {c.jogador_id for c in jogo.convocados}
    jogos_anteriores = db.query(Jogo).filter(
        Jogo.equipa_id == jogo.equipa_id,
        Jogo.id != jogo.id,
        Jogo.data <= jogo.data,
    ).order_by(Jogo.data.desc(), Jogo.id.desc()).limit(5).all()

    return templates.TemplateResponse(request, "jogos/detalhe.html", {
        "utilizador": utilizador,
        "jogo": jogo,
        "jogadores": jogadores,
        "convocados_ids": convocados_ids,
        "jogos_anteriores": jogos_anteriores,
    })


@router.get("/{jogo_id}/editar", response_class=HTMLResponse)
def form_editar_jogo(
    jogo_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    jogo = _obter_jogo(db, jogo_id)
    if not jogo:
        return RedirectResponse(url="/equipas")
    verificar_ou_negar_equipa(utilizador, jogo.equipa_id, db)

    return templates.TemplateResponse(request, "jogos/form.html", {
        "utilizador": utilizador,
        "jogo": jogo,
        "modo": "editar",
    })


@router.post("/{jogo_id}/editar")
async def editar_jogo(
    jogo_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
    data: str = Form(...),
    hora: str = Form(""),
    local: str = Form(""),
    adversario: str = Form(...),
    competicao: str = Form(""),
    em_casa: str = Form("true"),
    observacoes: str = Form(""),
):
    jogo = _obter_jogo(db, jogo_id)
    if not jogo:
        return RedirectResponse(url="/equipas")
    verificar_ou_negar_equipa(utilizador, jogo.equipa_id, db)

    _atualizar_campos_jogo(jogo, data, hora, local, adversario, competicao, em_casa, observacoes)
    db.commit()
    set_flash(request, "Jogo atualizado.")
    return RedirectResponse(url=f"/jogos/{jogo.id}", status_code=303)


@router.post("/{jogo_id}/eliminar")
async def eliminar_jogo(
    jogo_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    jogo = _obter_jogo(db, jogo_id)
    if not jogo:
        return RedirectResponse(url="/equipas")
    verificar_ou_negar_equipa(utilizador, jogo.equipa_id, db)

    equipa_id = jogo.equipa_id
    plano = db.query(PlanoJogo).filter(PlanoJogo.jogo_id == jogo.id).first()
    if plano:
        db.delete(plano)
    db.delete(jogo)
    db.commit()
    set_flash(request, "Jogo eliminado.")
    return RedirectResponse(url=f"/jogos/equipas/{equipa_id}", status_code=303)


@router.post("/{jogo_id}/resultado")
async def registar_resultado(
    jogo_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
    pontos_nos: str = Form(""),
    pontos_adversario: str = Form(""),
):
    jogo = _obter_jogo(db, jogo_id)
    if not jogo:
        return RedirectResponse(url="/equipas")
    verificar_ou_negar_equipa(utilizador, jogo.equipa_id, db)

    jogo.pontos_nos = int(pontos_nos) if pontos_nos else None
    jogo.pontos_adversario = int(pontos_adversario) if pontos_adversario else None
    db.commit()
    set_flash(request, "Resultado registado.")
    return RedirectResponse(url=f"/jogos/{jogo_id}", status_code=303)


@router.post("/{jogo_id}/convocatoria")
async def guardar_convocatoria(
    jogo_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
    hora_encontro: str = Form(""),
    local_encontro: str = Form(""),
    observacoes: str = Form(""),
):
    jogo = _obter_jogo(db, jogo_id)
    if not jogo:
        return RedirectResponse(url="/equipas")
    verificar_ou_negar_equipa(utilizador, jogo.equipa_id, db)

    dados = await request.form()
    jogadores_ids = [
        int(k.replace("jogador_", ""))
        for k in dados.keys()
        if k.startswith("jogador_")
    ]

    db.query(Convocado).filter(Convocado.jogo_id == jogo_id).delete()

    for jogador_id in jogadores_ids:
        jogador = db.query(Jogador).filter(Jogador.id == jogador_id).first()
        if not jogador or jogador.equipa_id != jogo.equipa_id:
            continue
        db.add(Convocado(
            jogo_id=jogo_id,
            jogador_id=jogador_id,
            hora_encontro=hora_encontro or None,
            local_encontro=local_encontro or None,
            observacoes=observacoes if observacoes and observacoes.strip() else None,
        ))

    db.commit()
    set_flash(request, "Convocatória atualizada.")
    return RedirectResponse(url=f"/jogos/{jogo_id}", status_code=303)


@router.post("/{jogo_id}/convocatoria/copiar/{origem_id}")
async def copiar_convocatoria(
    jogo_id: int,
    origem_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    """Reutiliza a última convocatória da equipa sem obrigar a marcar jogadoras uma a uma."""
    jogo = _obter_jogo(db, jogo_id)
    origem = _obter_jogo(db, origem_id)
    if not jogo or not origem or jogo.equipa_id != origem.equipa_id:
        return RedirectResponse(url=f"/jogos/{jogo_id}", status_code=303)
    verificar_ou_negar_equipa(utilizador, jogo.equipa_id, db)

    db.query(Convocado).filter(Convocado.jogo_id == jogo_id).delete()
    for convocado in origem.convocados:
        db.add(Convocado(
            jogo_id=jogo.id,
            jogador_id=convocado.jogador_id,
            hora_encontro=convocado.hora_encontro,
            local_encontro=convocado.local_encontro,
            observacoes=convocado.observacoes,
        ))
    db.commit()
    set_flash(request, f"Convocatória copiada de {origem.data}.")
    return RedirectResponse(url=f"/jogos/{jogo_id}", status_code=303)


@router.get("/{jogo_id}/plano", response_class=HTMLResponse)
def pagina_plano_jogo(
    jogo_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    jogo = _obter_jogo(db, jogo_id)
    if not jogo:
        return RedirectResponse(url="/equipas")
    verificar_ou_negar_equipa(utilizador, jogo.equipa_id, db)

    jogadores = db.query(Jogador).filter(Jogador.equipa_id == jogo.equipa_id).order_by(Jogador.nome).all()
    plano = db.query(PlanoJogo).filter(PlanoJogo.jogo_id == jogo_id).first()

    return templates.TemplateResponse(request, "jogos/plano_jogo.html", {
        "utilizador": utilizador,
        "jogo": jogo,
        "jogadores": jogadores,
        "plano": plano,
    })


@router.post("/{jogo_id}/plano")
async def guardar_plano_jogo(
    jogo_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    jogo = _obter_jogo(db, jogo_id)
    if not jogo:
        return RedirectResponse(url="/equipas")
    verificar_ou_negar_equipa(utilizador, jogo.equipa_id, db)

    dados = await request.form()

    plano = db.query(PlanoJogo).filter(PlanoJogo.jogo_id == jogo_id).first()
    if not plano:
        plano = PlanoJogo(jogo_id=jogo_id)
        db.add(plano)

    campos_texto = [
        "rotacoes", "chaves_ataque", "chaves_defesa", "movimentos_ofensivos",
        "bloqueio_direto_lateral", "bloqueio_direto_central", "handoff",
        "indiretos_entrada", "indiretos_saida", "bola_dentro",
        "situacoes_especiais", "reflexao",
    ]
    for campo in campos_texto:
        setattr(plano, campo, dados.get(campo) or None)

    for i in range(1, 6):
        val = dados.get(f"titular_{i}")
        setattr(plano, f"titular_{i}", int(val) if val else None)

    db.commit()
    set_flash(request, "Plano de jogo guardado.")
    return RedirectResponse(url=f"/jogos/{jogo_id}/plano", status_code=303)


@router.get("/{jogo_id}/convocatoria/print", response_class=HTMLResponse)
def imprimir_convocatoria(
    jogo_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    jogo = _obter_jogo(db, jogo_id)
    if not jogo:
        return RedirectResponse(url="/equipas")
    verificar_ou_negar_equipa(utilizador, jogo.equipa_id, db)

    return templates.TemplateResponse(request, "jogos/convocatoria_print.html", {
        "utilizador": utilizador,
        "jogo": jogo,
        "jogadores_convocados": [c.jogador for c in jogo.convocados],
        "identidade": getattr(request.state, "identidade_clube", {}),
    })


@router.get("/{jogo_id}/convocatoria/pdf")
def exportar_pdf_convocatoria(
    jogo_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    jogo = _obter_jogo(db, jogo_id)
    if not jogo:
        return RedirectResponse(url="/equipas")
    verificar_ou_negar_equipa(utilizador, jogo.equipa_id, db)
    pdf_bytes = renderizar_pdf(request, "jogos/convocatoria_print.html", {
        "utilizador": utilizador,
        "jogo": jogo,
        "jogadores_convocados": [c.jogador for c in jogo.convocados],
        "modo_pdf": True,
    })
    nome = f"convocatoria_{jogo.equipa.nome}_{jogo.data}.pdf".replace(" ", "_")
    return Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={nome}"})


@router.get("/{jogo_id}/plano/print", response_class=HTMLResponse)
def imprimir_plano_jogo(
    jogo_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    jogo = _obter_jogo(db, jogo_id)
    if not jogo:
        return RedirectResponse(url="/equipas")
    verificar_ou_negar_equipa(utilizador, jogo.equipa_id, db)

    jogadores = db.query(Jogador).filter(Jogador.equipa_id == jogo.equipa_id).all()
    jogadores_dict = {j.id: j for j in jogadores}

    return templates.TemplateResponse(request, "jogos/plano_jogo_print.html", {
        "utilizador": utilizador,
        "jogo": jogo,
        "plano": jogo.plano,
        "jogadores_dict": jogadores_dict,
        "identidade": getattr(request.state, "identidade_clube", {}),
    })


@router.get("/{jogo_id}/plano/pdf")
def exportar_pdf_plano_jogo(
    jogo_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    jogo = _obter_jogo(db, jogo_id)
    if not jogo:
        return RedirectResponse(url="/equipas")
    verificar_ou_negar_equipa(utilizador, jogo.equipa_id, db)
    jogadores = db.query(Jogador).filter(Jogador.equipa_id == jogo.equipa_id).all()
    jogadores_dict = {j.id: j for j in jogadores}
    pdf_bytes = renderizar_pdf(request, "jogos/plano_jogo_print.html", {
        "utilizador": utilizador,
        "jogo": jogo,
        "plano": jogo.plano,
        "jogadores_dict": jogadores_dict,
        "modo_pdf": True,
    })
    nome = f"plano_jogo_{jogo.equipa.nome}_{jogo.adversario}_{jogo.data}.pdf".replace(" ", "_")
    return Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={nome}"})

from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from template_config import Jinja2Templates
from sqlalchemy.orm import Session

from auth import verificar_perfil
from auth_deps import AcessoNegado, exigir_autenticacao, verificar_ou_negar_equipa
from database import get_db
from flash import set_flash
from models.equipa import Equipa
from models.jogador import Jogador
from models.jogo import (
    Convocado,
    ItemPlanoJogoBiblioteca,
    Jogo,
    PlanoJogo,
    PlanoJogoItem,
    PlanoJogoJogada,
    PlanoJogoRotacao,
)
from models.playbook import Playbook, SetPlay
from models.treinador import Treinador
from paths import TEMPLATES_DIR
from services.notificacoes_service import criar_notificacoes_para_equipa
from services.pdf_service import content_disposition_pdf, renderizar_pdf
from services.pdf_filtros_service import filtrar_jogos, obter_filtros_pdf
from services.jogos_service import (
    formatar_confronto,
    preparar_epocas_calendario_jogos,
    preparar_linhas_calendario_jogos,
)
from services.escaloes_service import escalao_imediatamente_inferior_da_equipa
from services.plano_jogo_service import (
    CAMPOS_POR_CATEGORIA,
    CATEGORIAS_PLANO,
    biblioteca_por_categoria,
    convocados_plano,
    graficos_plano,
    itens_por_categoria,
    jogo_em_preparacao,
    jogadas_disponiveis,
    materializar_campos_legados,
    normalizar_texto,
    preview_jogada,
    rotacoes_por_grupo,
    sincronizar_campos_legados,
    sincronizar_rotacoes_legadas,
)

router = APIRouter(prefix="/jogos")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _obter_jogo(db: Session, jogo_id: int):
    return db.query(Jogo).filter(Jogo.id == jogo_id).first()


def _obter_ou_criar_plano_jogo(db: Session, jogo: Jogo) -> PlanoJogo:
    """Mantém os dados de preparação e reflexão num único registo do jogo."""
    plano = db.query(PlanoJogo).filter(PlanoJogo.jogo_id == jogo.id).first()
    if plano:
        return plano
    plano = PlanoJogo(jogo_id=jogo.id, clube_id=jogo.clube_id)
    db.add(plano)
    return plano


def _destino_plano(dados, jogo_id: int) -> str:
    voltar = str(dados.get("voltar") or "")
    return voltar if voltar.startswith("/scouting/") and "//" not in voltar else f"/jogos/{jogo_id}/plano"


def _contexto_plano_estruturado(db: Session, jogo: Jogo, plano: PlanoJogo | None) -> dict:
    if plano and materializar_campos_legados(db, plano, jogo.equipa_id):
        db.commit()
    jogadas = list(plano.jogadas) if plano else []
    for relacao in jogadas:
        relacao.preview_imagem = preview_jogada(relacao.setplay)
    return {
        "jogadores": convocados_plano(jogo),
        "rotacoes_equipa": rotacoes_por_grupo(plano),
        "categorias_plano": CATEGORIAS_PLANO,
        "itens_plano": itens_por_categoria(plano),
        "biblioteca_plano": biblioteca_por_categoria(db, jogo.equipa_id),
        "jogadas_disponiveis": jogadas_disponiveis(db, jogo.equipa_id),
        "jogadas_plano": jogadas,
    }


def _verificar_acesso_plano_jogo(
    utilizador, jogo: Jogo, db: Session, permitir_consulta_staff: bool = True,
    permitir_jogo_passado: bool = False,
) -> None:
    """O staff consulta o plano, mas não pode alterar o respetivo conteúdo."""
    verificar_ou_negar_equipa(utilizador, jogo.equipa_id, db)
    if not permitir_jogo_passado and not jogo_em_preparacao(jogo):
        raise AcessoNegado(f"/jogos/{jogo.id}")
    if utilizador.perfil.value == "staff" and not permitir_consulta_staff:
        from auth_deps import SemPermissao
        raise SemPermissao(f"/jogos/{jogo.id}", status_code=403)


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


def _jogadores_ficha(jogadores):
    """Expõe a última altura registada sem alterar o perfil do atleta."""
    for jogador in jogadores:
        registos = sorted(
            jogador.registos_antropometricos or [],
            key=lambda item: item.data,
            reverse=True,
        )
        jogador.altura_ficha = registos[0].altura if registos else None
    return jogadores


def _jogadores_escalhao_inferior(db: Session, equipa: Equipa):
    """Devolve apenas reforços permitidos para treinos e jogos da equipa."""
    escalao_origem = escalao_imediatamente_inferior_da_equipa(equipa)
    if not escalao_origem:
        return []
    return db.query(Jogador).join(Equipa, Jogador.equipa_id == Equipa.id).filter(
        Jogador.clube_id == equipa.clube_id,
        Jogador.ativo.is_(True),
        Equipa.escalao == escalao_origem,
        Equipa.genero == equipa.genero,
    ).order_by(Jogador.numero_camisola, Jogador.nome).all()


def _jogadores_disponiveis_jogo(
    db: Session,
    jogo: Jogo,
    incluir_escalhao_inferior: bool = False,
    incluir_convocados: bool = False,
):
    """Plantel próprio, candidatos elegíveis e/ou reforços já convocados."""
    equipa = jogo.equipa
    plantel = db.query(Jogador).filter(
        Jogador.equipa_id == jogo.equipa_id,
        Jogador.ativo.is_(True),
    ).order_by(Jogador.numero_camisola, Jogador.nome).all()
    reforcos = _jogadores_escalhao_inferior(db, equipa) if incluir_escalhao_inferior else []
    if incluir_convocados:
        ids = {jogador.id for jogador in plantel + reforcos}
        reforcos.extend(
            convocado.jogador for convocado in jogo.convocados
            if convocado.jogador and convocado.jogador.ativo and convocado.jogador_id not in ids
        )
    return plantel + [jogador for jogador in reforcos if jogador.id not in {item.id for item in plantel}]


def _elementos_equipa_ficha(db: Session, equipa_id: int):
    equipa = db.query(Equipa).filter(Equipa.id == equipa_id).first()
    return sorted(
        list(equipa.treinadores if equipa else []),
        key=lambda elemento: ((elemento.funcao or "Treinador"), (elemento.nome or "").lower()),
    )


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
    jogos = filtrar_jogos(jogos, obter_filtros_pdf(request))
    nome_clube = _nome_clube_pedido(request, equipa)
    identidade = getattr(request.state, "identidade_clube", {}) or {}
    epocas_calendario = preparar_epocas_calendario_jogos(
        jogos,
        identidade.get("epoca_predefinida"),
    )
    pdf_bytes = renderizar_pdf(request, "jogos/calendario_pdf.html", {
        "utilizador": utilizador,
        "equipa": equipa,
        "jogos": jogos,
        "confrontos": _confrontos(jogos, nome_clube),
        "linhas_jogos": preparar_linhas_calendario_jogos(jogos, nome_clube),
        "epocas_calendario": epocas_calendario,
        "hoje": date.today(),
    })
    epoca_nome = epocas_calendario[-1]["epoca"].replace("/", "-")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": content_disposition_pdf(f"Calendário de jogos {epoca_nome}")},
    )


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
    numero_jogo: str = Form(""),
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
        numero_jogo=numero_jogo.strip() or None,
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

    jogadores = _jogadores_disponiveis_jogo(db, jogo, incluir_escalhao_inferior=True)
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
        "jogo_futuro": jogo_em_preparacao(jogo),
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
    numero_jogo: str = Form(""),
    em_casa: str = Form("true"),
    observacoes: str = Form(""),
):
    jogo = _obter_jogo(db, jogo_id)
    if not jogo:
        return RedirectResponse(url="/equipas")
    verificar_ou_negar_equipa(utilizador, jogo.equipa_id, db)

    _atualizar_campos_jogo(jogo, data, hora, local, adversario, competicao, em_casa, observacoes)
    jogo.numero_jogo = numero_jogo.strip() or None
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


@router.post("/{jogo_id}/reflexao")
def guardar_reflexao_jogo(
    jogo_id: int,
    request: Request,
    reflexao: str = Form(""),
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    """Guarda a mesma reflexão apresentada no jogo e no plano de jogo."""
    jogo = _obter_jogo(db, jogo_id)
    if not jogo:
        return RedirectResponse(url="/equipas")
    _verificar_acesso_plano_jogo(
        utilizador, jogo, db, permitir_consulta_staff=False, permitir_jogo_passado=True
    )

    plano = _obter_ou_criar_plano_jogo(db, jogo)
    plano.reflexao = reflexao.strip() or None
    db.commit()
    set_flash(request, "Reflexão do jogo guardada.")
    return RedirectResponse(url=f"/jogos/{jogo_id}#reflexao-jogo", status_code=303)


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

    jogadores_permitidos = {
        jogador.id: jogador
        for jogador in _jogadores_disponiveis_jogo(db, jogo, incluir_escalhao_inferior=True)
    }
    jogadores_ids = list(dict.fromkeys(jogadores_ids))
    excede_limite = len(jogadores_ids) > 12
    jogadores_ids = jogadores_ids[:12]
    for jogador_id in jogadores_ids:
        jogador = jogadores_permitidos.get(jogador_id)
        if not jogador:
            continue
        db.add(Convocado(
            jogo_id=jogo_id,
            jogador_id=jogador_id,
            hora_encontro=hora_encontro or None,
            local_encontro=local_encontro or None,
            observacoes=observacoes if observacoes and observacoes.strip() else None,
        ))

    db.commit()
    set_flash(request, "Convocatória atualizada com os primeiros 12 atletas." if excede_limite else "Convocatória atualizada.")
    return RedirectResponse(url=f"/jogos/{jogo_id}", status_code=303)


@router.post("/{jogo_id}/ficha-jogo/convocar-escalhao-inferior")
async def convocar_para_ficha_jogo(
    jogo_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
    jogador_ids: list[int] = Form(default=[]),
):
    """Adiciona reforços temporários à convocatória, sem mexer no plantel."""
    jogo = _obter_jogo(db, jogo_id)
    if not jogo:
        return RedirectResponse(url="/equipas")
    verificar_ou_negar_equipa(utilizador, jogo.equipa_id, db)
    permitidos = {jogador.id: jogador for jogador in _jogadores_escalhao_inferior(db, jogo.equipa)}
    existentes = {convocado.jogador_id for convocado in jogo.convocados}
    adicionados = 0
    for jogador_id in dict.fromkeys(jogador_ids):
        if jogador_id in permitidos and jogador_id not in existentes:
            db.add(Convocado(jogo_id=jogo.id, jogador_id=jogador_id))
            adicionados += 1
    if adicionados:
        db.commit()
        set_flash(request, f"{adicionados} atleta(s) do escalão inferior adicionado(s) à ficha.")
    else:
        set_flash(request, "Seleciona pelo menos um atleta elegível do escalão inferior.", "error")
    return RedirectResponse(url=f"/jogos/{jogo_id}/ficha-jogo", status_code=303)


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
    _verificar_acesso_plano_jogo(utilizador, jogo, db)

    plano = db.query(PlanoJogo).filter(PlanoJogo.jogo_id == jogo_id).first()
    contexto = {
        "utilizador": utilizador,
        "jogo": jogo,
        "plano": plano,
    }
    contexto.update(_contexto_plano_estruturado(db, jogo, plano))
    return templates.TemplateResponse(request, "jogos/plano_jogo.html", contexto)


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
    _verificar_acesso_plano_jogo(utilizador, jogo, db, permitir_consulta_staff=False)

    dados = await request.form()

    plano = _obter_ou_criar_plano_jogo(db, jogo)

    campos_texto = [
        "rotacoes", "chaves_ataque", "chaves_defesa", "movimentos_ofensivos",
        "bloqueio_direto_lateral", "bloqueio_direto_central", "handoff",
        "indiretos_entrada", "indiretos_saida", "bola_dentro",
        "situacoes_especiais", "reflexao",
    ]
    for campo in campos_texto:
        if campo in dados:
            setattr(plano, campo, dados.get(campo) or None)

    convocados_ids = {jogador.id for jogador in convocados_plano(jogo)}
    titulares_usados = set()
    for i in range(1, 6):
        val = dados.get(f"titular_{i}")
        jogador_id = int(val) if str(val or "").isdigit() else None
        if jogador_id not in convocados_ids or jogador_id in titulares_usados:
            jogador_id = None
        if jogador_id:
            titulares_usados.add(jogador_id)
        setattr(plano, f"titular_{i}", jogador_id)

    for grupo in range(1, 4):
        campo = f"rotacao_{grupo}_minuto"
        if campo in dados:
            bruto = str(dados.get(campo) or "").strip()
            minuto = int(bruto) if bruto.isdigit() else None
            setattr(plano, campo, minuto if minuto is not None and 1 <= minuto <= 60 else None)

    if any(f"rotacao_{grupo}_{ordem}" in dados for grupo in range(1, 4) for ordem in range(1, 6)):
        db.flush()
        db.query(PlanoJogoRotacao).filter(PlanoJogoRotacao.plano_jogo_id == plano.id).delete()
        for grupo in range(1, 4):
            usados = set()
            for ordem in range(1, 6):
                valor = dados.get(f"rotacao_{grupo}_{ordem}")
                jogador_id = int(valor) if str(valor or "").isdigit() else None
                if jogador_id not in convocados_ids or jogador_id in usados:
                    continue
                usados.add(jogador_id)
                db.add(PlanoJogoRotacao(
                    clube_id=jogo.clube_id,
                    plano_jogo_id=plano.id,
                    grupo=grupo,
                    ordem=ordem,
                    jogador_id=jogador_id,
                ))
        db.flush()
        db.expire(plano, ["grupos_rotacao"])
        sincronizar_rotacoes_legadas(plano)

    db.commit()
    set_flash(request, "Plano de jogo guardado.")
    return RedirectResponse(url=_destino_plano(dados, jogo_id), status_code=303)


@router.post("/{jogo_id}/plano/itens")
async def adicionar_item_plano(jogo_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_autenticacao)):
    jogo = _obter_jogo(db, jogo_id)
    dados = await request.form()
    if not jogo:
        return RedirectResponse(url="/equipas", status_code=303)
    _verificar_acesso_plano_jogo(utilizador, jogo, db, permitir_consulta_staff=False)
    categoria = str(dados.get("categoria") or "")
    if categoria not in CAMPOS_POR_CATEGORIA:
        return RedirectResponse(url=_destino_plano(dados, jogo_id), status_code=303)
    plano = _obter_ou_criar_plano_jogo(db, jogo)
    db.flush()
    if materializar_campos_legados(db, plano, jogo.equipa_id):
        db.flush()
        db.expire(plano, ["itens"])
    item_id = int(dados.get("item_id")) if str(dados.get("item_id") or "").isdigit() else None
    texto = str(dados.get("novo_texto") or "").strip()
    item = None
    if item_id:
        item = db.query(ItemPlanoJogoBiblioteca).filter(
            ItemPlanoJogoBiblioteca.id == item_id,
            ItemPlanoJogoBiblioteca.equipa_id == jogo.equipa_id,
            ItemPlanoJogoBiblioteca.categoria == categoria,
        ).first()
    elif texto:
        normalizado = normalizar_texto(texto)
        item = db.query(ItemPlanoJogoBiblioteca).filter(
            ItemPlanoJogoBiblioteca.equipa_id == jogo.equipa_id,
            ItemPlanoJogoBiblioteca.categoria == categoria,
            ItemPlanoJogoBiblioteca.texto_normalizado == normalizado,
        ).first()
        if not item:
            item = ItemPlanoJogoBiblioteca(
                clube_id=jogo.clube_id,
                equipa_id=jogo.equipa_id,
                categoria=categoria,
                texto=texto,
                texto_normalizado=normalizado,
            )
            db.add(item)
            db.flush()
        elif not item.ativo:
            item.ativo = True
    if item and not db.query(PlanoJogoItem).filter(
        PlanoJogoItem.plano_jogo_id == plano.id,
        PlanoJogoItem.item_id == item.id,
    ).first():
        atuais = [rel for rel in plano.itens if rel.item and rel.item.categoria == categoria]
        for ordem_atual, relacao_atual in enumerate(atuais):
            relacao_atual.ordem = ordem_atual
        ordem = len(atuais)
        db.add(PlanoJogoItem(clube_id=jogo.clube_id, plano_jogo_id=plano.id, item_id=item.id, ordem=ordem))
        db.flush()
        db.expire(plano, ["itens"])
        sincronizar_campos_legados(plano)
    db.commit()
    return RedirectResponse(url=_destino_plano(dados, jogo_id), status_code=303)


@router.post("/{jogo_id}/plano/biblioteca/{item_id}/eliminar")
async def eliminar_item_biblioteca_plano(jogo_id: int, item_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_autenticacao)):
    jogo = _obter_jogo(db, jogo_id)
    dados = await request.form()
    if not jogo:
        return RedirectResponse(url="/equipas", status_code=303)
    _verificar_acesso_plano_jogo(utilizador, jogo, db, permitir_consulta_staff=False)
    item = db.query(ItemPlanoJogoBiblioteca).filter(
        ItemPlanoJogoBiblioteca.id == item_id,
        ItemPlanoJogoBiblioteca.equipa_id == jogo.equipa_id,
    ).first()
    if item:
        # A remoção é lógica para preservar planos antigos que já usam esta opção.
        item.ativo = False
        db.commit()
    return RedirectResponse(url=_destino_plano(dados, jogo_id), status_code=303)


@router.post("/{jogo_id}/plano/itens/{relacao_id}/mover/{direcao}")
async def mover_item_plano(jogo_id: int, relacao_id: int, direcao: str, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_autenticacao)):
    jogo = _obter_jogo(db, jogo_id)
    dados = await request.form()
    if not jogo:
        return RedirectResponse(url="/equipas", status_code=303)
    _verificar_acesso_plano_jogo(utilizador, jogo, db, permitir_consulta_staff=False)
    relacao = db.query(PlanoJogoItem).join(PlanoJogo).filter(PlanoJogoItem.id == relacao_id, PlanoJogo.jogo_id == jogo.id).first()
    if relacao and direcao in {"cima", "baixo"}:
        pares = [item for item in relacao.plano.itens if item.item.categoria == relacao.item.categoria]
        for ordem, item in enumerate(pares):
            item.ordem = ordem
        indice = pares.index(relacao)
        destino = indice - 1 if direcao == "cima" else indice + 1
        if 0 <= destino < len(pares):
            relacao.ordem, pares[destino].ordem = pares[destino].ordem, relacao.ordem
            sincronizar_campos_legados(relacao.plano)
            db.commit()
    return RedirectResponse(url=_destino_plano(dados, jogo_id), status_code=303)


@router.post("/{jogo_id}/plano/itens/{relacao_id}/eliminar")
async def eliminar_item_plano(jogo_id: int, relacao_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_autenticacao)):
    jogo = _obter_jogo(db, jogo_id)
    dados = await request.form()
    if not jogo:
        return RedirectResponse(url="/equipas", status_code=303)
    _verificar_acesso_plano_jogo(utilizador, jogo, db, permitir_consulta_staff=False)
    relacao = db.query(PlanoJogoItem).join(PlanoJogo).filter(PlanoJogoItem.id == relacao_id, PlanoJogo.jogo_id == jogo.id).first()
    if relacao:
        plano = relacao.plano
        categoria = relacao.item.categoria
        db.delete(relacao)
        db.flush()
        restantes = [item for item in plano.itens if item.id != relacao_id and item.item.categoria == categoria]
        for ordem, item in enumerate(restantes):
            item.ordem = ordem
        db.expire(plano, ["itens"])
        sincronizar_campos_legados(plano)
        db.commit()
    return RedirectResponse(url=_destino_plano(dados, jogo_id), status_code=303)


@router.post("/{jogo_id}/plano/itens/eliminar-selecao")
async def eliminar_chaves_selecionadas(jogo_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_autenticacao)):
    jogo = _obter_jogo(db, jogo_id)
    dados = await request.form()
    if not jogo:
        return RedirectResponse(url="/equipas", status_code=303)
    _verificar_acesso_plano_jogo(utilizador, jogo, db, permitir_consulta_staff=False)
    categoria = str(dados.get("categoria") or "")
    if categoria not in {"chave_ataque", "chave_defesa"}:
        return RedirectResponse(url=_destino_plano(dados, jogo_id), status_code=303)
    ids = {int(valor) for valor in dados.getlist("relacao_ids") if str(valor).isdigit()}
    if ids:
        plano = db.query(PlanoJogo).filter(PlanoJogo.jogo_id == jogo.id).first()
        if plano:
            selecionadas = [
                relacao for relacao in plano.itens
                if relacao.id in ids and relacao.item.categoria == categoria
            ]
            for relacao in selecionadas:
                db.delete(relacao)
            db.flush()
            db.expire(plano, ["itens"])
            for ordem, relacao in enumerate(itens_por_categoria(plano)[categoria]):
                relacao.ordem = ordem
            sincronizar_campos_legados(plano)
            db.commit()
    return RedirectResponse(url=_destino_plano(dados, jogo_id), status_code=303)


@router.post("/{jogo_id}/plano/jogadas")
async def adicionar_jogada_plano(jogo_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_autenticacao)):
    jogo = _obter_jogo(db, jogo_id)
    dados = await request.form()
    if not jogo:
        return RedirectResponse(url="/equipas", status_code=303)
    _verificar_acesso_plano_jogo(utilizador, jogo, db, permitir_consulta_staff=False)
    pedidos = list(dict.fromkeys(
        int(valor) for valor in [*dados.getlist("setplay_ids"), dados.get("setplay_id")]
        if str(valor or "").isdigit()
    ))
    jogadas = db.query(SetPlay).join(Playbook).filter(
        SetPlay.id.in_(pedidos), Playbook.equipa_id == jogo.equipa_id,
    ).all() if pedidos else []
    disponiveis = {jogada.id: jogada for jogada in jogadas}
    plano = _obter_ou_criar_plano_jogo(db, jogo)
    db.flush()
    existentes = {relacao.setplay_id for relacao in plano.jogadas}
    ordem = max((relacao.ordem for relacao in plano.jogadas), default=-1) + 1
    adicionados = 0
    for setplay_id in pedidos:
        if setplay_id in disponiveis and setplay_id not in existentes:
            db.add(PlanoJogoJogada(clube_id=jogo.clube_id, plano_jogo_id=plano.id, setplay_id=setplay_id, ordem=ordem))
            existentes.add(setplay_id)
            ordem += 1
            adicionados += 1
    if adicionados:
        db.commit()
    return RedirectResponse(url=_destino_plano(dados, jogo_id), status_code=303)


@router.post("/{jogo_id}/plano/jogadas/{relacao_id}/mover/{direcao}")
async def mover_jogada_plano(jogo_id: int, relacao_id: int, direcao: str, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_autenticacao)):
    jogo = _obter_jogo(db, jogo_id)
    dados = await request.form()
    if not jogo:
        return RedirectResponse(url="/equipas", status_code=303)
    _verificar_acesso_plano_jogo(utilizador, jogo, db, permitir_consulta_staff=False)
    relacao = db.query(PlanoJogoJogada).join(PlanoJogo).filter(PlanoJogoJogada.id == relacao_id, PlanoJogo.jogo_id == jogo.id).first()
    if relacao and direcao in {"cima", "baixo"}:
        pares = list(relacao.plano.jogadas)
        indice = pares.index(relacao)
        destino = indice - 1 if direcao == "cima" else indice + 1
        if 0 <= destino < len(pares):
            relacao.ordem, pares[destino].ordem = pares[destino].ordem, relacao.ordem
            db.commit()
    return RedirectResponse(url=_destino_plano(dados, jogo_id), status_code=303)


@router.post("/{jogo_id}/plano/jogadas/{relacao_id}/eliminar")
async def eliminar_jogada_plano(jogo_id: int, relacao_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_autenticacao)):
    jogo = _obter_jogo(db, jogo_id)
    dados = await request.form()
    if not jogo:
        return RedirectResponse(url="/equipas", status_code=303)
    _verificar_acesso_plano_jogo(utilizador, jogo, db, permitir_consulta_staff=False)
    relacao = db.query(PlanoJogoJogada).join(PlanoJogo).filter(PlanoJogoJogada.id == relacao_id, PlanoJogo.jogo_id == jogo.id).first()
    if relacao:
        plano = relacao.plano
        db.delete(relacao)
        db.flush()
        for ordem, item in enumerate([item for item in plano.jogadas if item.id != relacao_id]):
            item.ordem = ordem
        db.commit()
    return RedirectResponse(url=_destino_plano(dados, jogo_id), status_code=303)


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
        "nome_clube": _nome_clube_pedido(request, jogo.equipa),
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
        "nome_clube": _nome_clube_pedido(request, jogo.equipa),
    })
    nome = f"convocatoria_{jogo.equipa.nome}_{jogo.data}.pdf".replace(" ", "_")
    return Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={nome}"})


@router.get("/{jogo_id}/ficha-jogo", response_class=HTMLResponse)
def selecionar_ficha_jogo(
    jogo_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    jogo = _obter_jogo(db, jogo_id)
    if not jogo:
        return RedirectResponse(url="/equipas")
    verificar_ou_negar_equipa(utilizador, jogo.equipa_id, db)
    jogadores = _jogadores_disponiveis_jogo(db, jogo, incluir_convocados=True)
    convocados_ids = {convocado.jogador_id for convocado in jogo.convocados}
    reforcos_disponiveis = [
        jogador for jogador in _jogadores_escalhao_inferior(db, jogo.equipa)
        if jogador.id not in convocados_ids
    ]
    return templates.TemplateResponse(request, "jogos/ficha_jogo.html", {
        "utilizador": utilizador,
        "jogo": jogo,
        "jogadores": _jogadores_ficha(jogadores),
        "reforcos_disponiveis": reforcos_disponiveis,
        "elementos_tecnicos": _elementos_equipa_ficha(db, jogo.equipa_id),
        "cores_equipamento": ("Branco", "Escuro", "Vermelho", "Azul", "Preto", "Amarelo", "Outro"),
    })


@router.post("/{jogo_id}/ficha-jogo/pdf")
async def exportar_ficha_jogo(
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
    jogadores_ids = {int(valor) for valor in dados.getlist("jogadores_ids") if str(valor).isdigit()}
    elementos_ids = {int(valor) for valor in dados.getlist("elementos_ids") if str(valor).isdigit()}
    capitao_id = int(dados.get("capitao_id")) if str(dados.get("capitao_id", "")).isdigit() else None
    cor_equipamento = str(dados.get("cor_equipamento", "")).strip()

    jogadores_disponiveis = {jogador.id: jogador for jogador in _jogadores_disponiveis_jogo(db, jogo, incluir_convocados=True)}
    jogadores = [jogadores_disponiveis[jogador_id] for jogador_id in jogadores_ids if jogador_id in jogadores_disponiveis]
    jogadores.sort(key=lambda jogador: (jogador.numero_camisola is None, jogador.numero_camisola or 0, jogador.nome))
    elementos_disponiveis = _elementos_equipa_ficha(db, jogo.equipa_id)
    elementos = [elemento for elemento in elementos_disponiveis if elemento.id in elementos_ids]

    if not jogadores:
        set_flash(request, "Seleciona pelo menos um jogador para a ficha de jogo.", "error")
        return RedirectResponse(url=f"/jogos/{jogo_id}/ficha-jogo", status_code=303)
    if capitao_id not in {jogador.id for jogador in jogadores}:
        set_flash(request, "O capitão deve ser um dos jogadores selecionados.", "error")
        return RedirectResponse(url=f"/jogos/{jogo_id}/ficha-jogo", status_code=303)
    if not cor_equipamento:
        set_flash(request, "Seleciona a cor do equipamento.", "error")
        return RedirectResponse(url=f"/jogos/{jogo_id}/ficha-jogo", status_code=303)

    pdf = renderizar_pdf(request, "jogos/ficha_jogo_pdf.html", {
        "utilizador": utilizador,
        "jogo": jogo,
        "jogadores": _jogadores_ficha(jogadores),
        "elementos_tecnicos": elementos,
        "capitao_id": capitao_id,
        "cor_equipamento": cor_equipamento,
    })
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": content_disposition_pdf(f"Ficha de jogo {jogo.equipa.nome} {jogo.data}")},
    )


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
    _verificar_acesso_plano_jogo(utilizador, jogo, db)

    jogadores = convocados_plano(jogo)
    jogadores_dict = {j.id: j for j in jogadores}

    return templates.TemplateResponse(request, "jogos/plano_jogo_print.html", {
        "utilizador": utilizador,
        "jogo": jogo,
        "plano": jogo.plano,
        "jogadores_dict": jogadores_dict,
        "rotacoes_equipa": rotacoes_por_grupo(jogo.plano),
        "graficos_plano": graficos_plano(jogo.plano),
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
    _verificar_acesso_plano_jogo(utilizador, jogo, db)
    jogadores = convocados_plano(jogo)
    jogadores_dict = {j.id: j for j in jogadores}
    pdf_bytes = renderizar_pdf(request, "jogos/plano_jogo_print.html", {
        "utilizador": utilizador,
        "jogo": jogo,
        "plano": jogo.plano,
        "jogadores_dict": jogadores_dict,
        "rotacoes_equipa": rotacoes_por_grupo(jogo.plano),
        "graficos_plano": graficos_plano(jogo.plano),
        "modo_pdf": True,
    })
    nome = f"plano_jogo_{jogo.equipa.nome}_{jogo.adversario}_{jogo.data}.pdf".replace(" ", "_")
    return Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={nome}"})

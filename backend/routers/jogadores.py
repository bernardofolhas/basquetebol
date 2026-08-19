from datetime import date

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from template_config import Jinja2Templates
from sqlalchemy.orm import Session, joinedload

from auth_deps import (
    AcessoNegado,
    exigir_autenticacao,
    exigir_coordenacao,
    exigir_operacao_desportiva,
    exigir_secretaria,
    verificar_ou_negar_equipa,
)
from auth import verificar_perfil
from database import get_db
from flash import set_flash
from models.equipa import Equipa
from models.fisico import TesteFisico
from models.jogador import Jogador, RegistoAntropometrico
from models.utilizador import PerfilEnum
from paths import TEMPLATES_DIR
from services.assiduidade_service import obter_relatorio_assiduidade_jogador
from services.pdf_service import renderizar_pdf
from services.desenho_service import imagem_estatica_data_uri
from services.fotografia_jogador_service import apagar_fotografia, caminho_fotografia, guardar_fotografia

router = APIRouter(prefix="/jogadores")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _calcular_idade(data_nascimento: date | None) -> int | None:
    if not data_nascimento:
        return None
    hoje = date.today()
    return hoje.year - data_nascimento.year - ((hoje.month, hoje.day) < (data_nascimento.month, data_nascimento.day))


def _equipas_para_utilizador(utilizador, db: Session) -> list:
    """Devolve as equipas acessíveis pelo utilizador atual."""
    if verificar_perfil(utilizador, ["administrador", "coordenador"]):
        return db.query(Equipa).all()
    if utilizador.treinador_id:
        from models.treinador import Treinador
        treinador = db.query(Treinador).options(
            joinedload(Treinador.equipas)
        ).filter(Treinador.id == utilizador.treinador_id).first()
        return treinador.equipas if treinador else []
    return []


def _verificar_acesso_jogador(utilizador, jogador: Jogador, db: Session) -> None:
    """Lança AcessoNegado se o utilizador não puder aceder ao jogador."""
    if verificar_perfil(utilizador, ["secretaria"]):
        return
    if jogador.equipa_id:
        verificar_ou_negar_equipa(utilizador, jogador.equipa_id, db)
    elif verificar_perfil(utilizador, ["treinador"]):
        raise AcessoNegado("/jogadores")


def _apagar_jogador_com_dependencias(db: Session, jogador: Jogador) -> str | None:
    """Desativa jogadores com histórico; elimina apenas registos sem dependências."""
    from models.assiduidade import RegistoAssiduidade
    from models.documento_jogador import DocumentoJogador
    from models.jogo import Convocado, PlanoJogo

    jogador_id = jogador.id
    plano = db.query(PlanoJogo).filter(
        (PlanoJogo.titular_1 == jogador_id)
        | (PlanoJogo.titular_2 == jogador_id)
        | (PlanoJogo.titular_3 == jogador_id)
        | (PlanoJogo.titular_4 == jogador_id)
        | (PlanoJogo.titular_5 == jogador_id)
    ).first()
    tem_historico = any([
        db.query(RegistoAssiduidade).filter(RegistoAssiduidade.jogador_id == jogador_id).first(),
        db.query(RegistoAntropometrico).filter(RegistoAntropometrico.jogador_id == jogador_id).first(),
        db.query(TesteFisico).filter(TesteFisico.jogador_id == jogador_id).first(),
        db.query(DocumentoJogador).filter(DocumentoJogador.jogador_id == jogador_id).first(),
        db.query(Convocado).filter(Convocado.jogador_id == jogador_id).first(), plano,
    ])
    if tem_historico:
        jogador.ativo = False
        jogador.equipa_id = None
        jogador.inscricao_estado = "inativo"
        return None
    fotografia = jogador.fotografia
    db.delete(jogador)
    return fotografia


@router.get("", response_class=HTMLResponse)
def listar_jogadores(
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    nome = request.query_params.get("nome", "").strip()
    equipa_filtro = request.query_params.get("equipa_id", "").strip()
    escalao = request.query_params.get("escalao", "").strip()
    estado = request.query_params.get("estado", "").strip()
    if verificar_perfil(utilizador, ["administrador", "coordenador"]):
        query = db.query(Jogador).options(joinedload(Jogador.equipa), joinedload(Jogador.registos_antropometricos)).filter(Jogador.ativo.is_(True))
        equipas = _equipas_para_utilizador(utilizador, db)
    else:
        equipas = _equipas_para_utilizador(utilizador, db)
        equipas_ids = [e.id for e in equipas]
        query = db.query(Jogador).options(joinedload(Jogador.equipa), joinedload(Jogador.registos_antropometricos)).filter(Jogador.ativo.is_(True))
        query = query.filter(Jogador.equipa_id.in_(equipas_ids)) if equipas_ids else query.filter(False)
    if nome:
        query = query.filter(Jogador.nome.ilike(f"%{nome}%"))
    if equipa_filtro.isdigit():
        query = query.filter(Jogador.equipa_id == int(equipa_filtro))
    if escalao:
        query = query.join(Equipa, Jogador.equipa_id == Equipa.id).filter(Equipa.escalao == escalao)
    if estado:
        query = query.filter(Jogador.inscricao_estado == estado)
    jogadores = query.order_by(Jogador.nome.asc()).all()
    for jogador in jogadores:
        registos = sorted(jogador.registos_antropometricos or [], key=lambda item: item.data, reverse=True)
        jogador.altura_atual = registos[0].altura if registos else None

    return templates.TemplateResponse(request, "jogadores/lista.html", {
        "utilizador": utilizador,
        "jogadores": jogadores,
        "equipas": equipas,
        "filtros": {"nome": nome, "equipa_id": equipa_filtro, "escalao": escalao, "estado": estado},
    })


@router.get("/novo", response_class=HTMLResponse)
def form_novo_jogador(
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    equipa_preselecionada = request.query_params.get("equipa_id", "").strip()
    return templates.TemplateResponse(request, "jogadores/form.html", {
        "utilizador": utilizador,
        "equipas": _equipas_para_utilizador(utilizador, db),
        "jogador": None,
        "equipa_preselecionada": int(equipa_preselecionada) if equipa_preselecionada.isdigit() else None,
    })


@router.post("/novo")
async def criar_jogador(
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
    nome: str = Form(...),
    data_nascimento: str = Form(""),
    naturalidade: str = Form(""),
    morada: str = Form(""),
    numero_camisola: str = Form(""),
    posicao: str = Form(""),
    telefone: str = Form(""),
    email: str = Form(""),
    nome_pai: str = Form(""),
    telefone_pai: str = Form(""),
    email_pai: str = Form(""),
    nome_mae: str = Form(""),
    telefone_mae: str = Form(""),
    email_mae: str = Form(""),
    equipa_id: str = Form(""),
    fotografia: UploadFile | None = File(None),
):
    if equipa_id:
        verificar_ou_negar_equipa(utilizador, int(equipa_id), db)

    try:
        fotografia_url = await guardar_fotografia(fotografia)
    except ValueError as erro:
        set_flash(request, str(erro), "error")
        return RedirectResponse(url="/jogadores/novo", status_code=303)

    jogador = Jogador(
        nome=nome,
        data_nascimento=date.fromisoformat(data_nascimento) if data_nascimento else None,
        naturalidade=naturalidade or None,
        morada=morada or None,
        numero_camisola=int(numero_camisola) if numero_camisola else None,
        posicao=posicao or None,
        telefone=telefone or None,
        email=email or None,
        nome_pai=nome_pai or None,
        telefone_pai=telefone_pai or None,
        email_pai=email_pai or None,
        nome_mae=nome_mae or None,
        telefone_mae=telefone_mae or None,
        email_mae=email_mae or None,
        equipa_id=int(equipa_id) if equipa_id else None,
        fotografia=fotografia_url,
    )

    db.add(jogador)
    db.commit()
    set_flash(request, f"Jogador '{nome}' registado com sucesso.")
    return RedirectResponse(url="/jogadores", status_code=303)


@router.post("/eliminar-selecionados")
async def eliminar_jogadores_selecionados(
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_coordenacao),
):
    form = await request.form()
    equipa_id_form = str(form.get("equipa_id", "")).strip()
    equipa_id = int(equipa_id_form) if equipa_id_form.isdigit() else None
    if equipa_id:
        verificar_ou_negar_equipa(utilizador, equipa_id, db)
    ids = sorted({int(valor) for valor in form.getlist("jogador_ids") if str(valor).isdigit()})
    query = db.query(Jogador).filter(Jogador.id.in_(ids))
    if equipa_id:
        query = query.filter(Jogador.equipa_id == equipa_id)
    jogadores = query.all() if ids else []
    retorno = f"/equipas/{equipa_id}/plantel" if equipa_id else "/jogadores"
    if not jogadores or str(len(jogadores)) != str(form.get("confirmar_total", "")):
        set_flash(request, "A confirmação não corresponde ao número de jogadores selecionados.", "error")
        return RedirectResponse(url=retorno, status_code=303)
    fotografias = [_apagar_jogador_com_dependencias(db, jogador) for jogador in jogadores]
    db.commit()
    for fotografia_url in fotografias:
        apagar_fotografia(fotografia_url)
    set_flash(request, f"{len(jogadores)} jogador(es) eliminados.")
    return RedirectResponse(url=retorno, status_code=303)


@router.post("/eliminar-todos")
async def eliminar_todos_jogadores(
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_coordenacao),
):
    form = await request.form()
    equipa_id_form = str(form.get("equipa_id", "")).strip()
    equipa_id = int(equipa_id_form) if equipa_id_form.isdigit() else None
    if equipa_id:
        verificar_ou_negar_equipa(utilizador, equipa_id, db)
    query = db.query(Jogador).filter(Jogador.ativo.is_(True))
    if equipa_id:
        query = query.filter(Jogador.equipa_id == equipa_id)
    jogadores = query.all()
    retorno = f"/equipas/{equipa_id}/plantel" if equipa_id else "/jogadores"
    if not jogadores or str(len(jogadores)) != str(form.get("confirmar_total", "")):
        set_flash(request, "Confirma o número total de jogadores antes de eliminar.", "error")
        return RedirectResponse(url=retorno, status_code=303)
    fotografias = [_apagar_jogador_com_dependencias(db, jogador) for jogador in jogadores]
    db.commit()
    for fotografia_url in fotografias:
        apagar_fotografia(fotografia_url)
    set_flash(request, f"Todos os {len(jogadores)} jogadores foram eliminados.")
    return RedirectResponse(url=retorno, status_code=303)


@router.get("/{jogador_id}", response_class=HTMLResponse)
def detalhe_jogador(
    jogador_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    jogador = db.query(Jogador).options(
        joinedload(Jogador.equipa),
        joinedload(Jogador.registos_antropometricos),
        joinedload(Jogador.documentos),
    ).filter(Jogador.id == jogador_id).first()
    if not jogador:
        return RedirectResponse(url="/jogadores")

    _verificar_acesso_jogador(utilizador, jogador, db)

    if utilizador.perfil == PerfilEnum.secretaria:
        return templates.TemplateResponse(request, "jogadores/detalhe_secretaria.html", {
            "utilizador": utilizador,
            "jogador": jogador,
            "idade": _calcular_idade(jogador.data_nascimento),
        })

    antropometrias = sorted(
        jogador.registos_antropometricos or [],
        key=lambda registo: registo.data,
        reverse=True,
    )
    testes = (
        db.query(TesteFisico)
        .filter(TesteFisico.jogador_id == jogador_id)
        .order_by(TesteFisico.data.desc(), TesteFisico.id.desc())
        .all()
    )
    evolucao = {
        "assiduidade": obter_relatorio_assiduidade_jogador(db, jogador_id),
        "antropometria_atual": antropometrias[0] if antropometrias else None,
        "antropometria_anterior": antropometrias[1] if len(antropometrias) > 1 else None,
        "testes_recentes": testes[:5],
        "teste_recente": testes[0] if testes else None,
    }

    return templates.TemplateResponse(request, "jogadores/detalhe.html", {
        "utilizador": utilizador,
        "jogador": jogador,
        "evolucao": evolucao,
        "idade": _calcular_idade(jogador.data_nascimento),
    })


@router.get("/{jogador_id}/evolucao/pdf")
def exportar_pdf_evolucao_jogador(
    jogador_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_operacao_desportiva),
):
    jogador = db.query(Jogador).options(
        joinedload(Jogador.equipa),
        joinedload(Jogador.registos_antropometricos),
        joinedload(Jogador.documentos),
    ).filter(Jogador.id == jogador_id).first()
    if not jogador:
        return RedirectResponse(url="/jogadores")
    _verificar_acesso_jogador(utilizador, jogador, db)

    antropometrias = sorted(
        jogador.registos_antropometricos or [],
        key=lambda registo: registo.data,
        reverse=True,
    )
    testes = (
        db.query(TesteFisico)
        .filter(TesteFisico.jogador_id == jogador_id)
        .order_by(TesteFisico.data.desc(), TesteFisico.id.desc())
        .all()
    )
    evolucao = {
        "assiduidade": obter_relatorio_assiduidade_jogador(db, jogador_id),
        "antropometrias": antropometrias,
        "testes": testes,
    }
    caminho_foto = caminho_fotografia(jogador.fotografia)
    jogador.fotografia_pdf = imagem_estatica_data_uri(caminho_foto, "image/jpeg") if caminho_foto else None
    pdf_bytes = renderizar_pdf(request, "jogadores/evolucao_pdf.html", {
        "utilizador": utilizador,
        "jogador": jogador,
        "evolucao": evolucao,
        "idade": _calcular_idade(jogador.data_nascimento),
    })
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=evolucao_{jogador.id}.pdf",
        },
    )


@router.post("/{jogador_id}/antropometria")
async def adicionar_antropometria(
    jogador_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_operacao_desportiva),
    data: str = Form(...),
    altura: str = Form(""),
    peso: str = Form(""),
    envergadura: str = Form(""),
    altura_sentado: str = Form(""),
):
    jogador = db.query(Jogador).filter(Jogador.id == jogador_id).first()
    if not jogador:
        return RedirectResponse(url="/jogadores")
    _verificar_acesso_jogador(utilizador, jogador, db)

    def _para_float(valor: str):
        try:
            return float(valor.replace(",", ".")) if valor else None
        except ValueError:
            return None

    registo = RegistoAntropometrico(
        jogador_id=jogador_id,
        data=date.fromisoformat(data),
        altura=_para_float(altura),
        peso=_para_float(peso),
        envergadura=_para_float(envergadura),
        altura_sentado=_para_float(altura_sentado),
    )

    db.add(registo)
    db.commit()
    set_flash(request, "Registo antropométrico adicionado.")
    return RedirectResponse(url=f"/jogadores/{jogador_id}", status_code=303)


@router.get("/{jogador_id}/editar", response_class=HTMLResponse)
def form_editar_jogador(
    jogador_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_operacao_desportiva),
):
    jogador = db.query(Jogador).filter(Jogador.id == jogador_id).first()
    if not jogador:
        return RedirectResponse(url="/jogadores")
    _verificar_acesso_jogador(utilizador, jogador, db)

    return templates.TemplateResponse(request, "jogadores/form.html", {
        "utilizador": utilizador,
        "jogador": jogador,
        "equipas": _equipas_para_utilizador(utilizador, db),
    })


@router.post("/{jogador_id}/editar")
async def editar_jogador(
    jogador_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_operacao_desportiva),
    nome: str = Form(...),
    data_nascimento: str = Form(""),
    naturalidade: str = Form(""),
    morada: str = Form(""),
    numero_camisola: str = Form(""),
    posicao: str = Form(""),
    telefone: str = Form(""),
    email: str = Form(""),
    nome_pai: str = Form(""),
    telefone_pai: str = Form(""),
    email_pai: str = Form(""),
    nome_mae: str = Form(""),
    telefone_mae: str = Form(""),
    email_mae: str = Form(""),
    equipa_id: str = Form(""),
    fotografia: UploadFile | None = File(None),
    remover_fotografia: str = Form("false"),
):
    jogador = db.query(Jogador).filter(Jogador.id == jogador_id).first()
    if not jogador:
        return RedirectResponse(url="/jogadores")
    _verificar_acesso_jogador(utilizador, jogador, db)

    if equipa_id:
        verificar_ou_negar_equipa(utilizador, int(equipa_id), db)

    jogador.nome = nome
    jogador.data_nascimento = date.fromisoformat(data_nascimento) if data_nascimento else None
    jogador.naturalidade = naturalidade or None
    jogador.morada = morada or None
    jogador.numero_camisola = int(numero_camisola) if numero_camisola else None
    jogador.posicao = posicao or None
    jogador.telefone = telefone or None
    jogador.email = email or None
    jogador.nome_pai = nome_pai or None
    jogador.telefone_pai = telefone_pai or None
    jogador.email_pai = email_pai or None
    jogador.nome_mae = nome_mae or None
    jogador.telefone_mae = telefone_mae or None
    jogador.email_mae = email_mae or None
    jogador.equipa_id = int(equipa_id) if equipa_id else None

    try:
        nova_fotografia = await guardar_fotografia(fotografia)
    except ValueError as erro:
        set_flash(request, str(erro), "error")
        return RedirectResponse(url=f"/jogadores/{jogador_id}/editar", status_code=303)
    fotografia_anterior = jogador.fotografia
    if remover_fotografia == "true":
        jogador.fotografia = None
    if nova_fotografia:
        jogador.fotografia = nova_fotografia

    db.commit()
    if (remover_fotografia == "true" or nova_fotografia) and fotografia_anterior:
        apagar_fotografia(fotografia_anterior)
    set_flash(request, f"Dados de '{nome}' atualizados.")
    return RedirectResponse(url=f"/jogadores/{jogador_id}", status_code=303)


@router.post("/{jogador_id}/apagar")
def apagar_jogador(
    jogador_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_coordenacao),
):
    jogador = db.query(Jogador).filter(Jogador.id == jogador_id).first()
    if jogador:
        nome = jogador.nome
        fotografia = _apagar_jogador_com_dependencias(db, jogador)
        db.commit()
        apagar_fotografia(fotografia)
        set_flash(request, f"Jogador '{nome}' apagado.")

    return RedirectResponse(url="/jogadores", status_code=303)


@router.post("/{jogador_id}/inscricao")
async def guardar_inscricao(
    jogador_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_secretaria),
    inscricao_estado: str = Form(""),
    inscricao_observacoes: str = Form(""),
    exame_medico_data: str = Form(""),
    exame_medico_validade: str = Form(""),
    exame_medico_estado: str = Form(""),
    exame_medico_observacoes: str = Form(""),
):
    jogador = db.query(Jogador).filter(Jogador.id == jogador_id).first()
    if not jogador:
        return RedirectResponse(url="/jogadores")
    _verificar_acesso_jogador(utilizador, jogador, db)

    jogador.inscricao_estado = inscricao_estado or None
    jogador.inscricao_observacoes = inscricao_observacoes or None
    jogador.exame_medico_data = date.fromisoformat(exame_medico_data) if exame_medico_data else None
    jogador.exame_medico_validade = date.fromisoformat(exame_medico_validade) if exame_medico_validade else None
    jogador.exame_medico_estado = exame_medico_estado or None
    jogador.exame_medico_observacoes = exame_medico_observacoes or None

    db.commit()
    set_flash(request, "Inscrição e exame médico atualizados.")
    return RedirectResponse(url=f"/jogadores/{jogador_id}", status_code=303)

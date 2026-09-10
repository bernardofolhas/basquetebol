from collections import defaultdict
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session, joinedload

from auth import encriptar_password
from auth_deps import exigir_atleta, exigir_operacao_desportiva, verificar_ou_negar_equipa
from database import get_db
from flash import set_flash
from models.equipa import Equipa
from models.jogador import Jogador
from models.questionario import RespostaQuestionarioDiario
from models.utilizador import Utilizador
from paths import TEMPLATES_DIR
from services.questionarios_service import criar_acesso_atleta
from template_config import Jinja2Templates


router = APIRouter(prefix="/questionarios")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _validar_escala(valor: int, nome: str, maximo: int = 10) -> None:
    if valor < 1 or valor > maximo:
        raise ValueError(f"{nome} deve estar entre 1 e {maximo}.")


@router.get("/diario", response_class=HTMLResponse)
def questionario_diario(
    request: Request,
    resposta_id: int | None = None,
    nova: bool = False,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_atleta),
):
    jogador = db.query(Jogador).options(joinedload(Jogador.equipa)).filter(
        Jogador.id == utilizador.jogador_id
    ).first()
    respostas_hoje = db.query(RespostaQuestionarioDiario).filter(
        RespostaQuestionarioDiario.jogador_id == utilizador.jogador_id,
        RespostaQuestionarioDiario.data == date.today(),
    ).order_by(
        RespostaQuestionarioDiario.criado_em.desc(),
        RespostaQuestionarioDiario.id.desc(),
    ).all()
    resposta = None
    if resposta_id is not None:
        resposta = db.query(RespostaQuestionarioDiario).filter(
            RespostaQuestionarioDiario.id == resposta_id,
            RespostaQuestionarioDiario.jogador_id == utilizador.jogador_id,
        ).first()
        if not resposta:
            set_flash(request, "A resposta que tentaste editar não foi encontrada.", "error")
            return RedirectResponse("/questionarios/diario", status_code=303)
    elif not nova and respostas_hoje:
        resposta = respostas_hoje[0]
    return templates.TemplateResponse(request, "questionarios/diario.html", {
        "utilizador": utilizador,
        "jogador": jogador,
        "resposta": resposta,
        "respostas_hoje": respostas_hoje,
        "nova_resposta": nova,
        "data_resposta": resposta.data if resposta else date.today(),
        "hoje": date.today(),
    })


@router.post("/diario")
def guardar_questionario_diario(
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_atleta),
    resposta_id: int | None = Form(None),
    tipo_sessao: str = Form(...),
    horas_sono: str = Form(""),
    qualidade_sono: int = Form(...),
    pse_esforco: int = Form(...),
    dor_membros_inferiores: int = Form(...),
    dor_membros_superiores: int = Form(...),
    tem_queixa: str = Form("nao"),
    descricao_queixa: str = Form(""),
    observacoes: str = Form(""),
):
    try:
        if tipo_sessao not in {"descanso", "treino", "jogo"}:
            raise ValueError("Seleciona o tipo de sessão de hoje.")
        _validar_escala(qualidade_sono, "A qualidade do sono", 5)
        _validar_escala(pse_esforco, "O esforço percebido")
        _validar_escala(dor_membros_inferiores, "A dor nos membros inferiores")
        _validar_escala(dor_membros_superiores, "A dor nos membros superiores")
        horas = float(horas_sono.replace(",", ".")) if horas_sono.strip() else None
        if horas is not None and not 0 <= horas <= 24:
            raise ValueError("As horas de sono devem estar entre 0 e 24.")
        tem_dor = tem_queixa == "sim"
        if tem_dor and not descricao_queixa.strip():
            raise ValueError("Descreve a dor ou queixa para a equipa técnica poder acompanhar.")
    except ValueError as erro:
        set_flash(request, str(erro), "error")
        return RedirectResponse("/questionarios/diario", status_code=303)

    resposta = None
    if resposta_id is not None:
        resposta = db.query(RespostaQuestionarioDiario).filter(
            RespostaQuestionarioDiario.id == resposta_id,
            RespostaQuestionarioDiario.jogador_id == utilizador.jogador_id,
        ).first()
        if not resposta:
            set_flash(request, "A resposta que tentaste editar não foi encontrada.", "error")
            return RedirectResponse("/questionarios/diario", status_code=303)
    if resposta is None:
        resposta = RespostaQuestionarioDiario(
            clube_id=utilizador.clube_id,
            jogador_id=utilizador.jogador_id,
            data=date.today(),
        )
        db.add(resposta)
    resposta.tipo_sessao = tipo_sessao
    resposta.horas_sono = horas
    resposta.qualidade_sono = qualidade_sono
    resposta.pse_esforco = pse_esforco
    resposta.dor_membros_inferiores = dor_membros_inferiores
    resposta.dor_membros_superiores = dor_membros_superiores
    resposta.tem_queixa = tem_dor
    resposta.descricao_queixa = descricao_queixa.strip() or None
    resposta.observacoes = observacoes.strip() or None
    db.commit()
    db.refresh(resposta)
    set_flash(request, "Resposta atualizada." if resposta_id else "Nova resposta guardada. Obrigado.")
    return RedirectResponse(f"/questionarios/diario?resposta_id={resposta.id}", status_code=303)


@router.get("/historico", response_class=HTMLResponse)
def historico_atleta(
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_atleta),
):
    jogador = db.query(Jogador).options(joinedload(Jogador.equipa)).filter(
        Jogador.id == utilizador.jogador_id
    ).first()
    respostas = db.query(RespostaQuestionarioDiario).filter(
        RespostaQuestionarioDiario.jogador_id == utilizador.jogador_id
    ).order_by(
        RespostaQuestionarioDiario.data.desc(),
        RespostaQuestionarioDiario.criado_em.desc(),
        RespostaQuestionarioDiario.id.desc(),
    ).limit(100).all()
    return templates.TemplateResponse(request, "questionarios/historico.html", {
        "utilizador": utilizador, "jogador": jogador, "respostas": respostas,
    })


@router.get("/equipas/{equipa_id}", response_class=HTMLResponse)
def painel_equipa(
    equipa_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_operacao_desportiva),
):
    verificar_ou_negar_equipa(utilizador, equipa_id, db)
    equipa = db.query(Equipa).filter(Equipa.id == equipa_id).first()
    if not equipa:
        return RedirectResponse("/equipas", status_code=303)
    jogadores = db.query(Jogador).filter(
        Jogador.equipa_id == equipa_id, Jogador.ativo.is_(True)
    ).order_by(Jogador.nome).all()
    acessos = {}
    for jogador in jogadores:
        conta, _ = criar_acesso_atleta(db, jogador)
        acessos[jogador.id] = conta
    db.commit()

    inicio = date.today() - timedelta(days=13)
    respostas = db.query(RespostaQuestionarioDiario).options(
        joinedload(RespostaQuestionarioDiario.jogador)
    ).filter(
        RespostaQuestionarioDiario.jogador_id.in_([j.id for j in jogadores]),
        RespostaQuestionarioDiario.data >= inicio,
    ).order_by(
        RespostaQuestionarioDiario.data.desc(),
        RespostaQuestionarioDiario.criado_em.desc(),
        RespostaQuestionarioDiario.id.desc(),
    ).all() if jogadores else []
    respostas_hoje = [r for r in respostas if r.data == date.today()]
    hoje_por_jogador = {}
    respostas_hoje_por_jogador = defaultdict(int)
    for resposta in respostas_hoje:
        hoje_por_jogador.setdefault(resposta.jogador_id, resposta)
        respostas_hoje_por_jogador[resposta.jogador_id] += 1
    alertas = [r for r in respostas_hoje if (
        r.tem_queixa or r.pse_esforco >= 8 or r.dor_membros_inferiores >= 7
        or r.dor_membros_superiores >= 7 or r.qualidade_sono <= 2
    )]
    por_data = defaultdict(list)
    for resposta in respostas:
        por_data[resposta.data].append(resposta)
    tendencia = []
    for deslocamento in range(13, -1, -1):
        dia = date.today() - timedelta(days=deslocamento)
        itens = por_data[dia]
        tendencia.append({
            "data": dia,
            "total": len(itens),
            "pse": round(sum(i.pse_esforco for i in itens) / len(itens), 1) if itens else None,
            "dor": max([max(i.dor_membros_inferiores, i.dor_membros_superiores) for i in itens], default=None),
        })

    return templates.TemplateResponse(request, "questionarios/painel.html", {
        "utilizador": utilizador,
        "equipa": equipa,
        "jogadores": jogadores,
        "acessos": acessos,
        "hoje_por_jogador": hoje_por_jogador,
        "respostas_hoje": respostas_hoje,
        "respostas_hoje_por_jogador": respostas_hoje_por_jogador,
        "alertas": sorted(alertas, key=lambda r: max(r.dor_membros_inferiores, r.dor_membros_superiores, r.pse_esforco), reverse=True),
        "tendencia": tendencia,
        "respondidos": len(hoje_por_jogador),
        "total": len(jogadores),
        "ligacao": str(request.base_url).rstrip("/") + "/questionarios/diario",
    })


@router.post("/atletas/{jogador_id}/repor-acesso")
def repor_acesso_atleta(
    jogador_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_operacao_desportiva),
):
    jogador = db.query(Jogador).filter(Jogador.id == jogador_id).first()
    if not jogador or not jogador.equipa_id:
        return RedirectResponse("/equipas", status_code=303)
    verificar_ou_negar_equipa(utilizador, jogador.equipa_id, db)
    conta, _ = criar_acesso_atleta(db, jogador)
    password = f"{conta.username}1234"
    conta.password_hash = encriptar_password(password)
    conta.deve_alterar_password = True
    conta.ativo = True
    conta.sessao_versao = (conta.sessao_versao or 0) + 1
    db.commit()
    set_flash(request, f"Acesso reposto: {conta.username} / {password}")
    return RedirectResponse(f"/questionarios/equipas/{jogador.equipa_id}", status_code=303)

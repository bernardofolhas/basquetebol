from collections import defaultdict
from datetime import date, timedelta
import json

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session, joinedload, selectinload

from auth import encriptar_password
from auth_deps import exigir_atleta, exigir_operacao_desportiva, verificar_ou_negar_equipa
from database import get_db
from flash import set_flash
from models.equipa import Equipa
from models.jogador import Jogador
from models.planeamento import Macrociclo, Mesociclo, Microciclo, SessaoTreino
from models.questionario import (
    AplicacaoQuestionario,
    PerguntaQuestionario,
    QuestionarioPersonalizado,
    RespostaPerguntaQuestionario,
    RespostaQuestionarioDiario,
    SubmissaoQuestionario,
)
from models.utilizador import Utilizador
from paths import TEMPLATES_DIR
from services.questionarios_service import criar_acesso_atleta
from services.questionarios_catalogo import MODELOS_QUESTIONARIO, TIPOS_PERGUNTA
from template_config import Jinja2Templates


router = APIRouter(prefix="/questionarios")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _validar_escala(valor: int, nome: str, maximo: int = 10) -> None:
    if valor < 1 or valor > maximo:
        raise ValueError(f"{nome} deve estar entre 1 e {maximo}.")


def _sessoes_da_equipa(db: Session, equipa_id: int):
    return db.query(SessaoTreino).join(Microciclo).join(Mesociclo).join(Macrociclo).filter(
        Macrociclo.equipa_id == equipa_id,
        SessaoTreino.ativa.is_(True),
    ).order_by(SessaoTreino.data.desc(), SessaoTreino.hora_inicio.desc()).limit(120).all()


def _normalizar_perguntas(perguntas_json: str) -> list[dict]:
    try:
        recebidas = json.loads(perguntas_json or "[]")
    except (TypeError, ValueError) as erro:
        raise ValueError("Não foi possível ler as perguntas do questionário.") from erro
    if not isinstance(recebidas, list) or not recebidas:
        raise ValueError("Adiciona pelo menos uma pergunta.")
    if len(recebidas) > 40:
        raise ValueError("Cada questionário pode ter até 40 perguntas.")
    resultado = []
    for indice, item in enumerate(recebidas):
        texto_pergunta = str(item.get("texto") or "").strip()
        tipo = str(item.get("tipo") or "").strip()
        if not texto_pergunta:
            raise ValueError(f"A pergunta {indice + 1} não tem texto.")
        if tipo not in TIPOS_PERGUNTA:
            raise ValueError(f"O tipo da pergunta {indice + 1} não é válido.")
        minimo = item.get("minimo")
        maximo = item.get("maximo")
        if tipo in {"escala", "numero"}:
            try:
                minimo = float(minimo)
                maximo = float(maximo)
            except (TypeError, ValueError) as erro:
                raise ValueError(f"Define os limites da pergunta {indice + 1}.") from erro
            if maximo <= minimo or (tipo == "escala" and maximo - minimo > 10):
                raise ValueError(f"Os limites da pergunta {indice + 1} não são válidos.")
        else:
            minimo = maximo = None
        opcoes = item.get("opcoes") if isinstance(item.get("opcoes"), list) else []
        opcoes = [str(opcao).strip() for opcao in opcoes if str(opcao).strip()]
        if tipo == "sim_nao":
            opcoes = ["Sim", "Não"]
        if tipo == "escolha" and len(opcoes) < 2:
            raise ValueError(f"Adiciona pelo menos duas opções à pergunta {indice + 1}.")
        resultado.append({
            "texto": texto_pergunta[:300],
            "ajuda": str(item.get("ajuda") or "").strip()[:300] or None,
            "tipo": tipo,
            "obrigatoria": bool(item.get("obrigatoria", True)),
            "minimo": minimo,
            "maximo": maximo,
            "rotulo_minimo": str(item.get("rotulo_minimo") or "").strip()[:80] or None,
            "rotulo_maximo": str(item.get("rotulo_maximo") or "").strip()[:80] or None,
            "opcoes": opcoes,
        })
    return resultado


def _obter_questionario_tecnico(db: Session, questionario_id: int, utilizador):
    questionario = db.query(QuestionarioPersonalizado).options(
        selectinload(QuestionarioPersonalizado.perguntas),
        selectinload(QuestionarioPersonalizado.aplicacoes),
    ).filter(QuestionarioPersonalizado.id == questionario_id).first()
    if questionario:
        verificar_ou_negar_equipa(utilizador, questionario.equipa_id, db)
    return questionario


def _obter_aplicacao_tecnica(db: Session, aplicacao_id: int, utilizador):
    aplicacao = db.query(AplicacaoQuestionario).options(
        joinedload(AplicacaoQuestionario.questionario).selectinload(QuestionarioPersonalizado.perguntas),
        selectinload(AplicacaoQuestionario.submissoes).selectinload(SubmissaoQuestionario.respostas),
        selectinload(AplicacaoQuestionario.submissoes).joinedload(SubmissaoQuestionario.jogador),
    ).filter(AplicacaoQuestionario.id == aplicacao_id).first()
    if aplicacao:
        verificar_ou_negar_equipa(utilizador, aplicacao.equipa_id, db)
    return aplicacao


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


@router.get("/equipas/{equipa_id}/biblioteca", response_class=HTMLResponse)
def biblioteca_questionarios(
    equipa_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_operacao_desportiva),
):
    verificar_ou_negar_equipa(utilizador, equipa_id, db)
    equipa = db.query(Equipa).filter(Equipa.id == equipa_id).first()
    if not equipa:
        return RedirectResponse("/equipas", status_code=303)
    questionarios = db.query(QuestionarioPersonalizado).options(
        selectinload(QuestionarioPersonalizado.perguntas),
        selectinload(QuestionarioPersonalizado.aplicacoes),
    ).filter(
        QuestionarioPersonalizado.equipa_id == equipa_id,
        QuestionarioPersonalizado.ativo.is_(True),
    ).order_by(QuestionarioPersonalizado.atualizado_em.desc()).all()
    return templates.TemplateResponse(request, "questionarios/biblioteca.html", {
        "utilizador": utilizador,
        "equipa": equipa,
        "questionarios": questionarios,
        "modelos": MODELOS_QUESTIONARIO,
    })


@router.get("/equipas/{equipa_id}/novo", response_class=HTMLResponse)
def novo_questionario(
    equipa_id: int,
    request: Request,
    modelo: str = "",
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_operacao_desportiva),
):
    verificar_ou_negar_equipa(utilizador, equipa_id, db)
    equipa = db.query(Equipa).filter(Equipa.id == equipa_id).first()
    if not equipa:
        return RedirectResponse("/equipas", status_code=303)
    selecionado = MODELOS_QUESTIONARIO.get(modelo)
    return templates.TemplateResponse(request, "questionarios/construtor.html", {
        "utilizador": utilizador,
        "equipa": equipa,
        "modelos": MODELOS_QUESTIONARIO,
        "modelo_chave": modelo if selecionado else "",
        "modelo": selecionado,
        "tipos_pergunta": TIPOS_PERGUNTA,
        "sessoes": _sessoes_da_equipa(db, equipa_id),
        "hoje": date.today(),
    })


@router.post("/equipas/{equipa_id}/criar")
def criar_questionario(
    equipa_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_operacao_desportiva),
    nome: str = Form(...),
    descricao: str = Form(""),
    modelo_chave: str = Form(""),
    perguntas_json: str = Form("[]"),
    data_aplicacao: str = Form(""),
    sessao_treino_id: str = Form(""),
    permite_multiplas: str = Form(""),
):
    verificar_ou_negar_equipa(utilizador, equipa_id, db)
    try:
        perguntas = _normalizar_perguntas(perguntas_json)
        nome_limpo = nome.strip()
        if not nome_limpo:
            raise ValueError("Indica um nome para o questionário.")
        sessao = None
        if sessao_treino_id.strip():
            sessao = db.query(SessaoTreino).join(Microciclo).join(Mesociclo).join(Macrociclo).filter(
                SessaoTreino.id == int(sessao_treino_id),
                Macrociclo.equipa_id == equipa_id,
            ).first()
            if not sessao:
                raise ValueError("O treino selecionado não pertence a esta equipa.")
        data_alvo = sessao.data if sessao else (date.fromisoformat(data_aplicacao) if data_aplicacao else None)
    except (TypeError, ValueError) as erro:
        set_flash(request, str(erro), "error")
        destino = f"/questionarios/equipas/{equipa_id}/novo"
        if modelo_chave in MODELOS_QUESTIONARIO:
            destino += f"?modelo={modelo_chave}"
        return RedirectResponse(destino, status_code=303)

    questionario = QuestionarioPersonalizado(
        clube_id=utilizador.clube_id,
        equipa_id=equipa_id,
        nome=nome_limpo[:180],
        descricao=descricao.strip() or None,
        origem_modelo=modelo_chave if modelo_chave in MODELOS_QUESTIONARIO else None,
    )
    db.add(questionario)
    db.flush()
    for ordem, item in enumerate(perguntas, start=1):
        db.add(PerguntaQuestionario(
            questionario_id=questionario.id,
            texto=item["texto"],
            ajuda=item["ajuda"],
            tipo=item["tipo"],
            obrigatoria=item["obrigatoria"],
            ordem=ordem,
            minimo=item["minimo"],
            maximo=item["maximo"],
            rotulo_minimo=item["rotulo_minimo"],
            rotulo_maximo=item["rotulo_maximo"],
            opcoes_json=json.dumps(item["opcoes"], ensure_ascii=False),
        ))
    if data_alvo:
        db.add(AplicacaoQuestionario(
            clube_id=utilizador.clube_id,
            equipa_id=equipa_id,
            questionario_id=questionario.id,
            sessao_treino_id=sessao.id if sessao else None,
            data=data_alvo,
            permite_multiplas=permite_multiplas == "sim",
        ))
    db.commit()
    set_flash(request, "Questionário criado" + (" e associado à data escolhida." if data_alvo else "."))
    return RedirectResponse(f"/questionarios/modelos/{questionario.id}", status_code=303)


@router.get("/modelos/{questionario_id}", response_class=HTMLResponse)
def detalhe_questionario(
    questionario_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_operacao_desportiva),
):
    questionario = _obter_questionario_tecnico(db, questionario_id, utilizador)
    if not questionario:
        return RedirectResponse("/equipas", status_code=303)
    return templates.TemplateResponse(request, "questionarios/detalhe.html", {
        "utilizador": utilizador,
        "questionario": questionario,
        "equipa": questionario.equipa,
        "sessoes": _sessoes_da_equipa(db, questionario.equipa_id),
        "hoje": date.today(),
        "base_url": str(request.base_url).rstrip("/"),
    })


@router.post("/modelos/{questionario_id}/aplicar")
def aplicar_questionario(
    questionario_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_operacao_desportiva),
    data_aplicacao: str = Form(""),
    sessao_treino_id: str = Form(""),
    titulo: str = Form(""),
    permite_multiplas: str = Form(""),
):
    questionario = _obter_questionario_tecnico(db, questionario_id, utilizador)
    if not questionario:
        return RedirectResponse("/equipas", status_code=303)
    try:
        sessao = None
        if sessao_treino_id.strip():
            sessao = db.query(SessaoTreino).join(Microciclo).join(Mesociclo).join(Macrociclo).filter(
                SessaoTreino.id == int(sessao_treino_id),
                Macrociclo.equipa_id == questionario.equipa_id,
            ).first()
            if not sessao:
                raise ValueError("O treino selecionado não pertence a esta equipa.")
        data_alvo = sessao.data if sessao else date.fromisoformat(data_aplicacao)
    except (TypeError, ValueError):
        set_flash(request, "Escolhe uma data ou um treino válido.", "error")
        return RedirectResponse(f"/questionarios/modelos/{questionario.id}", status_code=303)
    aplicacao = AplicacaoQuestionario(
        clube_id=questionario.clube_id,
        equipa_id=questionario.equipa_id,
        questionario_id=questionario.id,
        sessao_treino_id=sessao.id if sessao else None,
        data=data_alvo,
        titulo=titulo.strip()[:180] or None,
        permite_multiplas=permite_multiplas == "sim",
    )
    db.add(aplicacao)
    db.commit()
    db.refresh(aplicacao)
    set_flash(request, "Questionário aplicado à equipa.")
    return RedirectResponse(f"/questionarios/aplicacoes/{aplicacao.id}/resultados", status_code=303)


@router.get("/disponiveis", response_class=HTMLResponse)
def questionarios_disponiveis(
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_atleta),
):
    jogador = db.query(Jogador).filter(Jogador.id == utilizador.jogador_id).first()
    aplicacoes = db.query(AplicacaoQuestionario).options(
        joinedload(AplicacaoQuestionario.questionario),
        selectinload(AplicacaoQuestionario.submissoes),
    ).filter(
        AplicacaoQuestionario.equipa_id == jogador.equipa_id,
        AplicacaoQuestionario.ativa.is_(True),
        AplicacaoQuestionario.data >= date.today() - timedelta(days=30),
    ).order_by(AplicacaoQuestionario.data.desc()).all() if jogador and jogador.equipa_id else []
    return templates.TemplateResponse(request, "questionarios/disponiveis.html", {
        "utilizador": utilizador,
        "jogador": jogador,
        "aplicacoes": aplicacoes,
        "hoje": date.today(),
    })


@router.get("/responder/{aplicacao_id}", response_class=HTMLResponse)
def responder_questionario(
    aplicacao_id: int,
    request: Request,
    submissao_id: int | None = None,
    nova: bool = False,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_atleta),
):
    jogador = db.query(Jogador).filter(Jogador.id == utilizador.jogador_id).first()
    aplicacao = db.query(AplicacaoQuestionario).options(
        joinedload(AplicacaoQuestionario.questionario).selectinload(QuestionarioPersonalizado.perguntas),
        selectinload(AplicacaoQuestionario.submissoes).selectinload(SubmissaoQuestionario.respostas),
    ).filter(AplicacaoQuestionario.id == aplicacao_id).first()
    if not aplicacao or not jogador or aplicacao.equipa_id != jogador.equipa_id or not aplicacao.ativa:
        set_flash(request, "Este questionário não está disponível para a tua equipa.", "error")
        return RedirectResponse("/questionarios/disponiveis", status_code=303)
    if aplicacao.data > date.today():
        set_flash(request, "Este questionário ainda não está aberto.", "error")
        return RedirectResponse("/questionarios/disponiveis", status_code=303)
    submissoes = [item for item in aplicacao.submissoes if item.jogador_id == jogador.id]
    submissao = None
    if submissao_id is not None:
        submissao = next((item for item in submissoes if item.id == submissao_id), None)
        if not submissao:
            set_flash(request, "A resposta selecionada não foi encontrada.", "error")
            return RedirectResponse(f"/questionarios/responder/{aplicacao.id}", status_code=303)
    elif not nova and submissoes:
        submissao = submissoes[0]
    valores = {resposta.pergunta_id: resposta.valor for resposta in submissao.respostas} if submissao else {}
    return templates.TemplateResponse(request, "questionarios/responder.html", {
        "utilizador": utilizador,
        "jogador": jogador,
        "aplicacao": aplicacao,
        "submissoes": submissoes,
        "submissao": submissao,
        "valores": valores,
    })


@router.post("/responder/{aplicacao_id}")
async def guardar_resposta_personalizada(
    aplicacao_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_atleta),
):
    jogador = db.query(Jogador).filter(Jogador.id == utilizador.jogador_id).first()
    aplicacao = db.query(AplicacaoQuestionario).options(
        joinedload(AplicacaoQuestionario.questionario).selectinload(QuestionarioPersonalizado.perguntas)
    ).filter(AplicacaoQuestionario.id == aplicacao_id).first()
    if not aplicacao or not jogador or aplicacao.equipa_id != jogador.equipa_id or not aplicacao.ativa:
        return RedirectResponse("/questionarios/disponiveis", status_code=303)
    if aplicacao.data > date.today():
        set_flash(request, "Este questionário ainda não está aberto.", "error")
        return RedirectResponse("/questionarios/disponiveis", status_code=303)
    formulario = await request.form()
    submissao_id = formulario.get("submissao_id")
    submissao = None
    if submissao_id:
        try:
            submissao = db.query(SubmissaoQuestionario).filter(
                SubmissaoQuestionario.id == int(submissao_id),
                SubmissaoQuestionario.aplicacao_id == aplicacao.id,
                SubmissaoQuestionario.jogador_id == jogador.id,
            ).first()
        except (TypeError, ValueError):
            submissao = None
        if submissao is None:
            set_flash(request, "A resposta que tentaste editar não foi encontrada.", "error")
            return RedirectResponse(f"/questionarios/responder/{aplicacao.id}", status_code=303)
    if submissao is None and not aplicacao.permite_multiplas:
        submissao = db.query(SubmissaoQuestionario).filter(
            SubmissaoQuestionario.aplicacao_id == aplicacao.id,
            SubmissaoQuestionario.jogador_id == jogador.id,
        ).order_by(SubmissaoQuestionario.id.desc()).first()
    valores = {}
    try:
        for pergunta in aplicacao.questionario.perguntas:
            valor = str(formulario.get(f"pergunta_{pergunta.id}") or "").strip()
            if pergunta.obrigatoria and not valor:
                raise ValueError(f"Responde à pergunta: {pergunta.texto}")
            if valor and pergunta.tipo in {"escala", "numero"}:
                numero = float(valor.replace(",", "."))
                if numero < pergunta.minimo or numero > pergunta.maximo:
                    raise ValueError(f"A resposta a '{pergunta.texto}' está fora dos limites.")
                valor = str(int(numero)) if numero.is_integer() else str(numero)
            if valor and pergunta.tipo in {"escolha", "sim_nao"} and valor not in pergunta.opcoes:
                raise ValueError(f"A opção escolhida em '{pergunta.texto}' não é válida.")
            valores[pergunta.id] = valor
    except (TypeError, ValueError) as erro:
        set_flash(request, str(erro), "error")
        destino = f"/questionarios/responder/{aplicacao.id}"
        if submissao:
            destino += f"?submissao_id={submissao.id}"
        return RedirectResponse(destino, status_code=303)
    if submissao is None:
        submissao = SubmissaoQuestionario(
            clube_id=aplicacao.clube_id,
            aplicacao_id=aplicacao.id,
            jogador_id=jogador.id,
        )
        db.add(submissao)
        db.flush()
    else:
        db.query(RespostaPerguntaQuestionario).filter(
            RespostaPerguntaQuestionario.submissao_id == submissao.id
        ).delete(synchronize_session=False)
    for pergunta_id, valor in valores.items():
        db.add(RespostaPerguntaQuestionario(
            submissao_id=submissao.id,
            pergunta_id=pergunta_id,
            valor=valor or None,
        ))
    db.commit()
    set_flash(request, "Resposta atualizada." if submissao_id else "Questionário enviado. Obrigado.")
    return RedirectResponse("/questionarios/disponiveis", status_code=303)


@router.get("/aplicacoes/{aplicacao_id}/resultados", response_class=HTMLResponse)
def resultados_questionario(
    aplicacao_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_operacao_desportiva),
):
    aplicacao = _obter_aplicacao_tecnica(db, aplicacao_id, utilizador)
    if not aplicacao:
        return RedirectResponse("/equipas", status_code=303)
    jogadores_total = db.query(Jogador).filter(
        Jogador.equipa_id == aplicacao.equipa_id,
        Jogador.ativo.is_(True),
    ).count()
    analise = {}
    for pergunta in aplicacao.questionario.perguntas:
        valores = [
            resposta.valor for submissao in aplicacao.submissoes for resposta in submissao.respostas
            if resposta.pergunta_id == pergunta.id and resposta.valor not in (None, "")
        ]
        resumo = {"total": len(valores), "media": None, "opcoes": {}}
        if pergunta.tipo in {"escala", "numero"} and valores:
            numeros = [float(valor) for valor in valores]
            resumo["media"] = round(sum(numeros) / len(numeros), 1)
        if pergunta.tipo in {"escolha", "sim_nao"}:
            resumo["opcoes"] = {opcao: valores.count(opcao) for opcao in pergunta.opcoes}
        analise[pergunta.id] = resumo
    return templates.TemplateResponse(request, "questionarios/resultados.html", {
        "utilizador": utilizador,
        "aplicacao": aplicacao,
        "equipa": aplicacao.equipa,
        "analise": analise,
        "jogadores_total": jogadores_total,
        "atletas_respondidos": len({item.jogador_id for item in aplicacao.submissoes}),
        "ligacao": str(request.base_url).rstrip("/") + f"/questionarios/responder/{aplicacao.id}",
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

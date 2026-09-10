from collections import OrderedDict
from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session, joinedload

from auth_deps import exigir_operacao_desportiva, verificar_ou_negar_equipa
from database import get_db
from flash import set_flash
from models.avaliacao import AvaliacaoJogador, ParametroAvaliacao
from models.equipa import Equipa
from models.fisico import TesteFisico
from models.jogador import Jogador
from models.planeamento import Macrociclo, Mesociclo, Microciclo, SessaoTreino
from paths import TEMPLATES_DIR
from services.auditoria_service import registar_auditoria
from services.avaliacao_service import dados_dashboard_avaliacoes
from template_config import Jinja2Templates


router = APIRouter(prefix="/analise")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

CATEGORIAS = {
    "tecnica": "Técnica",
    "tatica": "Tática",
    "psicologica": "Psicológica",
    "fisica": "Física",
}

PARAMETROS_INICIAIS = {
    "tecnica": ["Passe", "Drible", "Lançamento", "Finalização", "Receção"],
    "tatica": ["Tomada de decisão", "Leitura do jogo", "Posicionamento", "Transição", "Jogo sem bola"],
    "psicologica": ["Concentração", "Confiança", "Comunicação", "Resiliência", "Compromisso"],
}


def _pode_editar(utilizador) -> bool:
    return utilizador.perfil.value in {
        "administrador", "coordenador", "treinador", "staff", "fisioterapeuta", "superadministrador"
    }


def _garantir_parametros_iniciais(db: Session, equipa: Equipa) -> None:
    if db.query(ParametroAvaliacao.id).filter(ParametroAvaliacao.equipa_id == equipa.id).first():
        return
    ordem = 0
    for categoria, nomes in PARAMETROS_INICIAIS.items():
        for nome in nomes:
            ordem += 1
            db.add(ParametroAvaliacao(
                clube_id=equipa.clube_id,
                equipa_id=equipa.id,
                nome=nome,
                categoria=categoria,
                valor_minimo=0,
                valor_maximo=5,
                ordem=ordem,
            ))
    db.commit()


def _obter_equipa(db: Session, equipa_id: int, utilizador) -> Equipa | None:
    verificar_ou_negar_equipa(utilizador, equipa_id, db)
    return db.query(Equipa).filter(Equipa.id == equipa_id).first()


def _equipa_id_da_sessao(db: Session, sessao_id: int) -> int | None:
    return db.query(Macrociclo.equipa_id).select_from(SessaoTreino).join(
        Microciclo, SessaoTreino.microciclo_id == Microciclo.id
    ).join(
        Mesociclo, Microciclo.mesociclo_id == Mesociclo.id
    ).join(
        Macrociclo, Mesociclo.macrociclo_id == Macrociclo.id
    ).filter(SessaoTreino.id == sessao_id).scalar()


def _normalizar_numero(valor) -> float:
    return float(str(valor).strip().replace(",", "."))


def _resposta_erro(request: Request, mensagem: str, status_code: int = 400):
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JSONResponse({"ok": False, "message": mensagem}, status_code=status_code)
    set_flash(request, mensagem, "erro")
    return RedirectResponse(request.headers.get("referer") or "/dashboard", status_code=303)


@router.get("/equipas/{equipa_id}", response_class=HTMLResponse)
def painel_equipa(
    equipa_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_operacao_desportiva),
):
    equipa = _obter_equipa(db, equipa_id, utilizador)
    if not equipa:
        return RedirectResponse("/equipas", status_code=303)
    _garantir_parametros_iniciais(db, equipa)

    jogadores = db.query(Jogador).filter(
        Jogador.equipa_id == equipa.id,
        Jogador.ativo.is_(True),
    ).order_by(Jogador.numero_camisola.asc().nullslast(), Jogador.nome).all()
    parametros = db.query(ParametroAvaliacao).filter(
        ParametroAvaliacao.equipa_id == equipa.id,
        ParametroAvaliacao.ativo.is_(True),
    ).order_by(ParametroAvaliacao.categoria, ParametroAvaliacao.ordem, ParametroAvaliacao.nome).all()
    avaliacoes = db.query(AvaliacaoJogador).options(
        joinedload(AvaliacaoJogador.jogador),
        joinedload(AvaliacaoJogador.parametro),
        joinedload(AvaliacaoJogador.sessao),
    ).filter(AvaliacaoJogador.equipa_id == equipa.id).order_by(
        AvaliacaoJogador.data.desc(), AvaliacaoJogador.id.desc()
    ).all()

    resumo_jogadores = []
    for jogador in jogadores:
        registos = [item for item in avaliacoes if item.jogador_id == jogador.id]
        medias = {}
        for categoria in ("tecnica", "tatica", "psicologica"):
            valores = [item.valor for item in registos if item.parametro.categoria == categoria]
            medias[categoria] = round(sum(valores) / len(valores), 1) if valores else None
        resumo_jogadores.append({
            "jogador": jogador,
            "medias": medias,
            "ultima_data": max((item.data for item in registos), default=None),
            "total": len(registos),
        })

    momentos = OrderedDict()
    for item in avaliacoes:
        chave = (item.data, item.sessao_id)
        momento = momentos.setdefault(chave, {
            "data": item.data,
            "sessao": item.sessao,
            "jogadores": set(),
            "parametros": set(),
        })
        momento["jogadores"].add(item.jogador_id)
        momento["parametros"].add(item.parametro_id)

    return templates.TemplateResponse(request, "avaliacoes/painel.html", {
        "utilizador": utilizador,
        "equipa": equipa,
        "jogadores": jogadores,
        "resumo_jogadores": resumo_jogadores,
        "parametros": parametros,
        "parametros_por_categoria": {
            categoria: [item for item in parametros if item.categoria == categoria]
            for categoria in CATEGORIAS
        },
        "categorias": CATEGORIAS,
        "momentos": list(momentos.values())[:8],
        "total_avaliacoes": len(avaliacoes),
        "jogadores_avaliados": len({item.jogador_id for item in avaliacoes}),
        "testes_fisicos_existentes": db.query(TesteFisico).join(Jogador).filter(Jogador.equipa_id == equipa.id).count(),
        "pode_editar": _pode_editar(utilizador),
        "dados_dashboard": dados_dashboard_avaliacoes(avaliacoes),
        "jogadores_dashboard": [
            {"id": jogador.id, "nome": jogador.nome} for jogador in jogadores
        ],
        "parametros_dashboard": [
            {
                "id": parametro.id,
                "nome": parametro.nome,
                "categoria": parametro.categoria,
                "unidade": parametro.unidade or ("/5" if parametro.categoria != "fisica" else ""),
            }
            for parametro in parametros
        ],
    })


@router.get("/equipas/{equipa_id}/registar", response_class=HTMLResponse)
def registar_avaliacoes(
    equipa_id: int,
    request: Request,
    sessao_id: int | None = None,
    data_avaliacao: date | None = None,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_operacao_desportiva),
):
    equipa = _obter_equipa(db, equipa_id, utilizador)
    if not equipa:
        return RedirectResponse("/equipas", status_code=303)
    if not _pode_editar(utilizador):
        return _resposta_erro(request, "Sem permissão para registar avaliações.", 403)
    _garantir_parametros_iniciais(db, equipa)

    sessao = None
    if sessao_id is not None:
        if _equipa_id_da_sessao(db, sessao_id) != equipa.id:
            return _resposta_erro(request, "A sessão não pertence a esta equipa.", 403)
        sessao = db.query(SessaoTreino).filter(SessaoTreino.id == sessao_id).first()

    jogadores = db.query(Jogador).filter(
        Jogador.equipa_id == equipa.id,
        Jogador.ativo.is_(True),
    ).order_by(Jogador.numero_camisola.asc().nullslast(), Jogador.nome).all()
    parametros = db.query(ParametroAvaliacao).filter(
        ParametroAvaliacao.equipa_id == equipa.id,
        ParametroAvaliacao.ativo.is_(True),
    ).order_by(ParametroAvaliacao.categoria, ParametroAvaliacao.ordem, ParametroAvaliacao.nome).all()
    existentes = []
    if sessao:
        existentes = db.query(AvaliacaoJogador).filter(
            AvaliacaoJogador.equipa_id == equipa.id,
            AvaliacaoJogador.sessao_id == sessao.id,
        ).all()
    elif data_avaliacao:
        existentes = db.query(AvaliacaoJogador).filter(
            AvaliacaoJogador.equipa_id == equipa.id,
            AvaliacaoJogador.sessao_id.is_(None),
            AvaliacaoJogador.data == data_avaliacao,
        ).all()

    return templates.TemplateResponse(request, "avaliacoes/registar.html", {
        "utilizador": utilizador,
        "equipa": equipa,
        "jogadores": jogadores,
        "parametros": parametros,
        "parametros_por_categoria": {
            categoria: [item for item in parametros if item.categoria == categoria]
            for categoria in CATEGORIAS
        },
        "categorias": CATEGORIAS,
        "sessao": sessao,
        "data_avaliacao": sessao.data if sessao else (data_avaliacao or date.today()),
        "valores_existentes": {
            f"{item.jogador_id}:{item.parametro_id}": item.valor for item in existentes
        },
        "jogadores_selecionados": {item.jogador_id for item in existentes},
        "parametros_selecionados": {item.parametro_id for item in existentes},
    })


@router.post("/equipas/{equipa_id}/registar")
async def guardar_avaliacoes(
    equipa_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_operacao_desportiva),
):
    equipa = _obter_equipa(db, equipa_id, utilizador)
    if not equipa or not _pode_editar(utilizador):
        return _resposta_erro(request, "Sem permissão para registar avaliações.", 403)

    form = await request.form()
    try:
        data_avaliacao = date.fromisoformat(str(form.get("data") or ""))
    except ValueError:
        return _resposta_erro(request, "Indica uma data de avaliação válida.")

    try:
        jogador_ids = {int(valor) for valor in form.getlist("jogador_ids")}
        parametro_ids = {int(valor) for valor in form.getlist("parametro_ids")}
        sessao_id = int(form.get("sessao_id")) if form.get("sessao_id") else None
    except (TypeError, ValueError):
        return _resposta_erro(request, "A seleção de atletas ou parâmetros é inválida.")
    if not jogador_ids or not parametro_ids:
        return _resposta_erro(request, "Seleciona pelo menos um atleta e um parâmetro.")
    if sessao_id and _equipa_id_da_sessao(db, sessao_id) != equipa.id:
        return _resposta_erro(request, "A sessão não pertence a esta equipa.", 403)

    jogadores = db.query(Jogador).filter(
        Jogador.id.in_(jogador_ids),
        Jogador.equipa_id == equipa.id,
        Jogador.ativo.is_(True),
    ).all()
    parametros = db.query(ParametroAvaliacao).filter(
        ParametroAvaliacao.id.in_(parametro_ids),
        ParametroAvaliacao.equipa_id == equipa.id,
        ParametroAvaliacao.ativo.is_(True),
    ).all()
    if len(jogadores) != len(jogador_ids) or len(parametros) != len(parametro_ids):
        return _resposta_erro(request, "A seleção contém dados que não pertencem a esta equipa.", 403)

    valores = []
    for jogador in jogadores:
        for parametro in parametros:
            bruto = form.get(f"valor_{jogador.id}_{parametro.id}")
            if bruto is None or not str(bruto).strip():
                continue
            try:
                valor = _normalizar_numero(bruto)
            except ValueError:
                return _resposta_erro(request, f"O valor de {parametro.nome} para {jogador.nome} não é válido.")
            minimo = 0 if parametro.categoria in {"tecnica", "tatica", "psicologica"} else parametro.valor_minimo
            maximo = 5 if parametro.categoria in {"tecnica", "tatica", "psicologica"} else parametro.valor_maximo
            if valor < minimo or valor > maximo:
                return _resposta_erro(
                    request,
                    f"{parametro.nome}: o valor deve estar entre {minimo:g} e {maximo:g}.",
                )
            valores.append((jogador, parametro, valor))
    if not valores:
        return _resposta_erro(request, "Preenche pelo menos um valor antes de guardar.")

    for jogador, parametro, valor in valores:
        consulta = db.query(AvaliacaoJogador).filter(
            AvaliacaoJogador.equipa_id == equipa.id,
            AvaliacaoJogador.jogador_id == jogador.id,
            AvaliacaoJogador.parametro_id == parametro.id,
            AvaliacaoJogador.data == data_avaliacao,
        )
        consulta = consulta.filter(
            AvaliacaoJogador.sessao_id == sessao_id if sessao_id else AvaliacaoJogador.sessao_id.is_(None)
        )
        registo = consulta.first()
        if registo:
            registo.valor = valor
            registo.avaliador_id = utilizador.id
        else:
            db.add(AvaliacaoJogador(
                clube_id=equipa.clube_id,
                equipa_id=equipa.id,
                jogador_id=jogador.id,
                parametro_id=parametro.id,
                sessao_id=sessao_id,
                avaliador_id=utilizador.id,
                data=data_avaliacao,
                valor=valor,
            ))

    registar_auditoria(
        db, utilizador, "registar", "avaliacoes_jogadores", None,
        f"{len(valores)} valor(es) · {equipa.nome} · {data_avaliacao.strftime('%d/%m/%Y')}", request,
    )
    db.commit()
    mensagem = f"{len(valores)} avaliação(ões) guardada(s)."
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JSONResponse({"ok": True, "message": mensagem, "redirect": f"/analise/equipas/{equipa.id}"})
    set_flash(request, mensagem)
    return RedirectResponse(f"/analise/equipas/{equipa.id}", status_code=303)


@router.post("/equipas/{equipa_id}/parametros")
async def criar_parametro(
    equipa_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_operacao_desportiva),
):
    equipa = _obter_equipa(db, equipa_id, utilizador)
    if not equipa or not _pode_editar(utilizador):
        return _resposta_erro(request, "Sem permissão para gerir parâmetros.", 403)
    form = await request.form()
    nome = str(form.get("nome") or "").strip()
    categoria = str(form.get("categoria") or "").strip()
    if not nome or categoria not in CATEGORIAS:
        return _resposta_erro(request, "Indica um nome e uma categoria válidos.")
    try:
        minimo = _normalizar_numero(form.get("valor_minimo") or 0)
        maximo = _normalizar_numero(form.get("valor_maximo") or (5 if categoria != "fisica" else 100))
    except ValueError:
        return _resposta_erro(request, "Os limites do parâmetro não são válidos.")
    if categoria != "fisica":
        minimo, maximo = 0, 5
    if maximo <= minimo:
        return _resposta_erro(request, "O valor máximo tem de ser superior ao mínimo.")

    parametro = ParametroAvaliacao(
        clube_id=equipa.clube_id,
        equipa_id=equipa.id,
        nome=nome,
        categoria=categoria,
        descricao=str(form.get("descricao") or "").strip() or None,
        valor_minimo=minimo,
        valor_maximo=maximo,
        unidade=str(form.get("unidade") or "").strip() or None,
        ordem=db.query(ParametroAvaliacao).filter(ParametroAvaliacao.equipa_id == equipa.id).count() + 1,
    )
    db.add(parametro)
    db.flush()
    registar_auditoria(db, utilizador, "criar", "parametro_avaliacao", parametro.id, nome, request)
    db.commit()
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JSONResponse({
            "ok": True,
            "message": "Parâmetro criado.",
            "parametro": {
                "id": parametro.id,
                "nome": parametro.nome,
                "categoria": parametro.categoria,
                "categoria_label": CATEGORIAS[parametro.categoria],
                "minimo": parametro.valor_minimo,
                "maximo": parametro.valor_maximo,
                "unidade": parametro.unidade or "",
            },
        })
    set_flash(request, "Parâmetro criado.")
    return RedirectResponse(f"/analise/equipas/{equipa.id}", status_code=303)


@router.post("/parametros/{parametro_id}/editar")
async def editar_parametro(
    parametro_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_operacao_desportiva),
):
    parametro = db.query(ParametroAvaliacao).filter(ParametroAvaliacao.id == parametro_id).first()
    if not parametro:
        return _resposta_erro(request, "Parâmetro não encontrado.", 404)
    _obter_equipa(db, parametro.equipa_id, utilizador)
    if not _pode_editar(utilizador):
        return _resposta_erro(request, "Sem permissão para gerir parâmetros.", 403)
    form = await request.form()
    nome = str(form.get("nome") or "").strip()
    if not nome:
        return _resposta_erro(request, "O nome do parâmetro é obrigatório.")
    parametro.nome = nome
    parametro.descricao = str(form.get("descricao") or "").strip() or None
    if parametro.categoria == "fisica":
        try:
            minimo = _normalizar_numero(form.get("valor_minimo") or 0)
            maximo = _normalizar_numero(form.get("valor_maximo") or 100)
        except ValueError:
            return _resposta_erro(request, "Os limites do parâmetro não são válidos.")
        if maximo <= minimo:
            return _resposta_erro(request, "O valor máximo tem de ser superior ao mínimo.")
        parametro.valor_minimo = minimo
        parametro.valor_maximo = maximo
        parametro.unidade = str(form.get("unidade") or "").strip() or None
    registar_auditoria(db, utilizador, "editar", "parametro_avaliacao", parametro.id, nome, request)
    db.commit()
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JSONResponse({"ok": True, "message": "Parâmetro atualizado."})
    set_flash(request, "Parâmetro atualizado.")
    return RedirectResponse(f"/analise/equipas/{parametro.equipa_id}", status_code=303)


@router.post("/parametros/{parametro_id}/eliminar")
def eliminar_parametro(
    parametro_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_operacao_desportiva),
):
    parametro = db.query(ParametroAvaliacao).filter(ParametroAvaliacao.id == parametro_id).first()
    if not parametro:
        return _resposta_erro(request, "Parâmetro não encontrado.", 404)
    _obter_equipa(db, parametro.equipa_id, utilizador)
    if not _pode_editar(utilizador):
        return _resposta_erro(request, "Sem permissão para gerir parâmetros.", 403)
    parametro.ativo = False
    registar_auditoria(db, utilizador, "eliminar", "parametro_avaliacao", parametro.id, parametro.nome, request)
    db.commit()
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JSONResponse({"ok": True, "message": "Parâmetro removido."})
    set_flash(request, "Parâmetro removido.")
    return RedirectResponse(f"/analise/equipas/{parametro.equipa_id}", status_code=303)


@router.get("/jogadores/{jogador_id}", response_class=HTMLResponse)
def detalhe_jogador(
    jogador_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_operacao_desportiva),
):
    jogador = db.query(Jogador).filter(Jogador.id == jogador_id).first()
    if not jogador or not jogador.equipa_id:
        return RedirectResponse("/equipas", status_code=303)
    verificar_ou_negar_equipa(utilizador, jogador.equipa_id, db)
    avaliacoes = db.query(AvaliacaoJogador).options(
        joinedload(AvaliacaoJogador.jogador),
        joinedload(AvaliacaoJogador.parametro),
        joinedload(AvaliacaoJogador.sessao),
    ).filter(AvaliacaoJogador.jogador_id == jogador.id).order_by(
        AvaliacaoJogador.data.desc(), AvaliacaoJogador.id.desc()
    ).all()
    medias = {}
    totais_categoria = {}
    for categoria in CATEGORIAS:
        valores = [item.valor for item in avaliacoes if item.parametro.categoria == categoria]
        totais_categoria[categoria] = len(valores)
        medias[categoria] = (
            round(sum(valores) / len(valores), 1)
            if valores and categoria != "fisica"
            else None
        )
    return templates.TemplateResponse(request, "avaliacoes/jogador.html", {
        "utilizador": utilizador,
        "jogador": jogador,
        "equipa": jogador.equipa,
        "avaliacoes": avaliacoes,
        "medias": medias,
        "totais_categoria": totais_categoria,
        "categorias": CATEGORIAS,
        "dados_dashboard": dados_dashboard_avaliacoes(avaliacoes),
        "jogadores_dashboard": [{"id": jogador.id, "nome": jogador.nome}],
        "parametros_dashboard": [
            {
                "id": item.parametro_id,
                "nome": item.parametro.nome,
                "categoria": item.parametro.categoria,
                "unidade": item.parametro.unidade or ("/5" if item.parametro.categoria != "fisica" else ""),
            }
            for item in avaliacoes
        ],
    })

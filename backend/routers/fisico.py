from datetime import date
from uuid import uuid4

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from template_config import Jinja2Templates
from sqlalchemy.orm import Session

from auth_deps import exigir_autenticacao, verificar_ou_negar_equipa
from database import get_db
from flash import set_flash
from models.equipa import Equipa
from models.fisico import DefinicaoTesteFisico, PlaneamentoFisico, TesteFisico
from models.jogador import Jogador
from paths import TEMPLATES_DIR

router = APIRouter(prefix="/fisico")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _pode_editar_fisico(utilizador) -> bool:
    return utilizador.perfil.value in {
        "administrador", "coordenador", "treinador", "staff", "fisioterapeuta", "superadministrador"
    }


def _resultado_numerico(valor: str) -> float | None:
    valor = (valor or "").strip().replace(",", ".")
    return float(valor) if valor else None


def _lateralidade(valor: str) -> str:
    return "unilateral" if (valor or "").strip().lower() == "unilateral" else "bilateral"


def _calcular_assimetria(esquerdo: float | None, direito: float | None) -> float | None:
    if esquerdo is None or direito is None:
        return None
    referencia = max(abs(esquerdo), abs(direito))
    return round(abs(esquerdo - direito) / referencia * 100, 2) if referencia else 0.0


def _obter_ou_criar_definicao(
    db: Session,
    clube_id: int,
    nome: str,
    lateralidade: str = "bilateral",
    unidade_total: str | None = None,
    unidade_esquerda: str | None = None,
    unidade_direita: str | None = None,
) -> DefinicaoTesteFisico:
    definicao = db.query(DefinicaoTesteFisico).filter(
        DefinicaoTesteFisico.clube_id == clube_id,
        DefinicaoTesteFisico.nome.ilike(nome.strip()),
    ).first()
    if definicao:
        return definicao
    definicao = DefinicaoTesteFisico(
        clube_id=clube_id,
        nome=nome.strip(),
        lateralidade=_lateralidade(lateralidade),
        unidade_total=(unidade_total or "").strip() or None,
        unidade_esquerda=(unidade_esquerda or "").strip() or None,
        unidade_direita=(unidade_direita or "").strip() or None,
    )
    db.add(definicao)
    db.flush()
    return definicao


def _sincronizar_catalogo_legado(db: Session, equipa: Equipa) -> list[DefinicaoTesteFisico]:
    """Transforma nomes de testes antigos em definições reutilizáveis."""
    definicoes = db.query(DefinicaoTesteFisico).filter(
        DefinicaoTesteFisico.clube_id == equipa.clube_id,
        DefinicaoTesteFisico.ativo.is_(True),
    ).order_by(DefinicaoTesteFisico.nome).all()
    por_nome = {item.nome.strip().casefold(): item for item in definicoes}
    legados = db.query(TesteFisico).join(Jogador).filter(
        Jogador.equipa_id == equipa.id,
        TesteFisico.definicao_id.is_(None),
    ).all()
    alterado = False
    for teste in legados:
        chave = teste.tipo_teste.strip().casefold()
        definicao = por_nome.get(chave)
        if not definicao:
            definicao = _obter_ou_criar_definicao(
                db, equipa.clube_id, teste.tipo_teste,
                unidade_total=teste.unidade,
            )
            definicoes.append(definicao)
            por_nome[chave] = definicao
        teste.definicao_id = definicao.id
        teste.lateralidade = definicao.lateralidade
        teste.medicao_id = teste.medicao_id or f"legado-{teste.id}"
        alterado = True
    if alterado:
        db.commit()
    return sorted(definicoes, key=lambda item: item.nome.casefold())


@router.get("/jogadores/{jogador_id}", response_class=HTMLResponse)
def testes_jogador(
    jogador_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    jogador = db.query(Jogador).filter(Jogador.id == jogador_id).first()
    if not jogador:
        return RedirectResponse(url="/jogadores")
    if not jogador.equipa_id:
        return RedirectResponse(url="/jogadores")
    verificar_ou_negar_equipa(utilizador, jogador.equipa_id, db)

    testes = db.query(TesteFisico).filter(
        TesteFisico.jogador_id == jogador_id
    ).order_by(TesteFisico.data.desc()).all()

    testes_por_tipo: dict = {}
    for teste in testes:
        testes_por_tipo.setdefault(teste.tipo_teste, []).append(teste)

    return templates.TemplateResponse(request, "fisico/testes.html", {
        "utilizador": utilizador,
        "jogador": jogador,
        "testes": testes,
        "testes_por_tipo": testes_por_tipo,
    })


@router.post("/jogadores/{jogador_id}/novo")
async def adicionar_teste(
    jogador_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
    data: str = Form(...),
    tipo_teste: str = Form(...),
    resultado: str = Form(""),
    unidade: str = Form(""),
    observacoes: str = Form(""),
):
    jogador = db.query(Jogador).filter(Jogador.id == jogador_id).first()
    if not jogador:
        return RedirectResponse(url="/jogadores")
    if not jogador.equipa_id:
        return RedirectResponse(url="/jogadores")
    verificar_ou_negar_equipa(utilizador, jogador.equipa_id, db)
    if not _pode_editar_fisico(utilizador):
        set_flash(request, "Sem permissão para registar testes físicos.", "erro")
        return RedirectResponse(url=f"/fisico/jogadores/{jogador_id}", status_code=303)

    try:
        data_teste = date.fromisoformat(data)
        resultado_teste = _resultado_numerico(resultado)
    except ValueError:
        set_flash(request, "Confirma a data e o resultado do teste.", "erro")
        return RedirectResponse(url=f"/fisico/jogadores/{jogador_id}", status_code=303)

    db.add(TesteFisico(
        clube_id=jogador.clube_id,
        data=data_teste,
        tipo_teste=tipo_teste.strip(),
        resultado=resultado_teste,
        unidade=unidade.strip() or None,
        observacoes=observacoes.strip() or None,
        jogador_id=jogador_id,
        definicao=_obter_ou_criar_definicao(db, jogador.clube_id, tipo_teste, unidade_total=unidade),
        medicao_id=str(uuid4()),
    ))
    db.commit()
    set_flash(request, f"Teste '{tipo_teste}' adicionado.")
    return RedirectResponse(url=f"/fisico/jogadores/{jogador_id}", status_code=303)


@router.get("/equipas/{equipa_id}", response_class=HTMLResponse)
def planeamento_equipa(
    equipa_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    verificar_ou_negar_equipa(utilizador, equipa_id, db)

    equipa = db.query(Equipa).filter(Equipa.id == equipa_id).first()
    if not equipa:
        return RedirectResponse(url="/equipas")

    planeamentos = db.query(PlaneamentoFisico).filter(
        PlaneamentoFisico.equipa_id == equipa_id
    ).order_by(PlaneamentoFisico.data_inicio.desc()).all()

    jogadores = db.query(Jogador).filter(
        Jogador.equipa_id == equipa_id,
        Jogador.ativo.is_(True),
    ).order_by(Jogador.numero_camisola.asc().nullslast(), Jogador.nome).all()
    definicoes = _sincronizar_catalogo_legado(db, equipa)
    testes = db.query(TesteFisico).join(Jogador).filter(
        Jogador.equipa_id == equipa_id,
    ).order_by(TesteFisico.data.desc(), TesteFisico.id.desc()).all()
    testes_por_definicao = []
    for definicao in definicoes:
        resultados = [teste for teste in testes if teste.definicao_id == definicao.id]
        if not resultados:
            continue
        testes_por_definicao.append({
            "definicao": definicao,
            "resultados": resultados,
            "medicoes": len({teste.medicao_id or f"legado-{teste.id}" for teste in resultados}),
            "atletas": len({teste.jogador_id for teste in resultados}),
            "ultima_data": max(teste.data for teste in resultados),
        })
    dados_analise = [{
        "id": teste.id,
        "definicao_id": teste.definicao_id,
        "teste": teste.tipo_teste,
        "data": teste.data.isoformat(),
        "jogador_id": teste.jogador_id,
        "jogador": teste.jogador.nome,
        "resultado": teste.resultado,
        "esquerdo": teste.resultado_esquerdo,
        "direito": teste.resultado_direito,
        "assimetria": teste.assimetria_percentual,
        "unidade": teste.unidade,
    } for teste in testes]

    return templates.TemplateResponse(request, "fisico/planeamento.html", {
        "utilizador": utilizador,
        "equipa": equipa,
        "planeamentos": planeamentos,
        "jogadores": jogadores,
        "testes": testes,
        "definicoes_testes": definicoes,
        "testes_por_definicao": testes_por_definicao,
        "dados_analise": dados_analise,
        "vista": request.query_params.get("vista", "testes"),
        "pode_editar": _pode_editar_fisico(utilizador),
        "hoje": date.today(),
    })


@router.post("/equipas/{equipa_id}/testes")
async def criar_testes_equipa(
    equipa_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    verificar_ou_negar_equipa(utilizador, equipa_id, db)
    equipa = db.query(Equipa).filter(Equipa.id == equipa_id).first()
    if not equipa:
        return RedirectResponse(url="/equipas", status_code=303)
    if not _pode_editar_fisico(utilizador):
        set_flash(request, "Sem permissão para registar testes físicos.", "erro")
        return RedirectResponse(url=f"/fisico/equipas/{equipa_id}", status_code=303)

    form = await request.form()
    try:
        data_teste = date.fromisoformat(str(form.get("data") or ""))
    except ValueError:
        set_flash(request, "Indica uma data válida para o teste.", "erro")
        return RedirectResponse(url=f"/fisico/equipas/{equipa_id}#testes-fisicos", status_code=303)

    tipo_teste = str(form.get("tipo_teste") or "").strip()
    definicao_id = str(form.get("definicao_id") or "").strip()
    observacoes = str(form.get("observacoes") or "").strip() or None
    try:
        jogadores_ids = {int(valor) for valor in form.getlist("jogador_ids")}
    except (TypeError, ValueError):
        jogadores_ids = set()
    definicao = None
    if definicao_id.isdigit():
        definicao = db.query(DefinicaoTesteFisico).filter(
            DefinicaoTesteFisico.id == int(definicao_id),
            DefinicaoTesteFisico.clube_id == equipa.clube_id,
            DefinicaoTesteFisico.ativo.is_(True),
        ).first()
    if not definicao and not tipo_teste:
        set_flash(request, "Seleciona um teste do catálogo ou cria um novo.", "erro")
        return RedirectResponse(url=f"/fisico/equipas/{equipa_id}#testes-fisicos", status_code=303)
    if not jogadores_ids:
        set_flash(request, "Indica o tipo de teste e seleciona pelo menos um atleta.", "erro")
        return RedirectResponse(url=f"/fisico/equipas/{equipa_id}#testes-fisicos", status_code=303)

    if not definicao:
        definicao = _obter_ou_criar_definicao(
            db,
            equipa.clube_id,
            tipo_teste,
            str(form.get("lateralidade") or "bilateral"),
            str(form.get("unidade_total") or form.get("unidade") or ""),
            str(form.get("unidade_esquerda") or ""),
            str(form.get("unidade_direita") or ""),
        )

    jogadores = db.query(Jogador).filter(
        Jogador.equipa_id == equipa_id,
        Jogador.id.in_(jogadores_ids),
        Jogador.ativo.is_(True),
    ).all()
    if len(jogadores) != len(jogadores_ids):
        set_flash(request, "Existe um atleta inválido na seleção.", "erro")
        return RedirectResponse(url=f"/fisico/equipas/{equipa_id}#testes-fisicos", status_code=303)

    novos_testes = []
    medicao_id = str(uuid4())
    try:
        for jogador in jogadores:
            esquerdo = _resultado_numerico(str(form.get(f"resultado_esquerdo_{jogador.id}") or ""))
            direito = _resultado_numerico(str(form.get(f"resultado_direito_{jogador.id}") or ""))
            assimetria = _resultado_numerico(str(form.get(f"assimetria_{jogador.id}") or ""))
            if assimetria is None:
                assimetria = _calcular_assimetria(esquerdo, direito)
            novos_testes.append(TesteFisico(
                clube_id=equipa.clube_id,
                jogador_id=jogador.id,
                data=data_teste,
                tipo_teste=definicao.nome,
                resultado=_resultado_numerico(str(form.get(f"resultado_{jogador.id}") or "")),
                unidade=definicao.unidade_total,
                resultado_esquerdo=esquerdo,
                resultado_direito=direito,
                unidade_esquerda=definicao.unidade_esquerda,
                unidade_direita=definicao.unidade_direita,
                assimetria_percentual=assimetria,
                lateralidade=definicao.lateralidade,
                medicao_id=medicao_id,
                definicao_id=definicao.id,
                observacoes=observacoes,
            ))
    except ValueError:
        set_flash(request, "Os resultados devem ser valores numéricos.", "erro")
        return RedirectResponse(url=f"/fisico/equipas/{equipa_id}#testes-fisicos", status_code=303)

    db.add_all(novos_testes)
    db.commit()
    set_flash(request, f"Teste '{definicao.nome}' registado para {len(novos_testes)} atleta(s).")
    return RedirectResponse(url=f"/fisico/equipas/{equipa_id}#testes-fisicos", status_code=303)


@router.post("/equipas/{equipa_id}/novo")
async def criar_planeamento(
    equipa_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
    data_inicio: str = Form(...),
    data_fim: str = Form(...),
    tipo: str = Form("Semanal"),
    resistencia: str = Form(""),
    velocidade: str = Form(""),
    forca: str = Form(""),
    flexibilidade: str = Form(""),
    coordenacao: str = Form(""),
    observacoes: str = Form(""),
):
    verificar_ou_negar_equipa(utilizador, equipa_id, db)

    db.add(PlaneamentoFisico(
        clube_id=db.query(Equipa.clube_id).filter(Equipa.id == equipa_id).scalar(),
        data_inicio=date.fromisoformat(data_inicio),
        data_fim=date.fromisoformat(data_fim),
        tipo=tipo,
        resistencia=resistencia or None,
        velocidade=velocidade or None,
        forca=forca or None,
        flexibilidade=flexibilidade or None,
        coordenacao=coordenacao or None,
        observacoes=observacoes or None,
        equipa_id=equipa_id,
    ))
    db.commit()
    set_flash(request, "Planeamento físico criado.")
    return RedirectResponse(url=f"/fisico/equipas/{equipa_id}?vista=planeamento", status_code=303)

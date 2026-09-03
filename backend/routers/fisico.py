from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from template_config import Jinja2Templates
from sqlalchemy.orm import Session

from auth_deps import exigir_autenticacao, verificar_ou_negar_equipa
from database import get_db
from flash import set_flash
from models.equipa import Equipa
from models.fisico import PlaneamentoFisico, TesteFisico
from models.jogador import Jogador
from paths import TEMPLATES_DIR

router = APIRouter(prefix="/fisico")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _pode_editar_fisico(utilizador) -> bool:
    return utilizador.perfil.value in {
        "administrador", "coordenador", "treinador", "staff", "superadministrador"
    }


def _resultado_numerico(valor: str) -> float | None:
    valor = (valor or "").strip().replace(",", ".")
    return float(valor) if valor else None


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
    testes = db.query(TesteFisico).join(Jogador).filter(
        Jogador.equipa_id == equipa_id,
    ).order_by(TesteFisico.data.desc(), TesteFisico.id.desc()).limit(60).all()
    tipos_testes = []
    for teste in testes:
        sugestao = (teste.tipo_teste, teste.unidade or "")
        if sugestao not in tipos_testes:
            tipos_testes.append(sugestao)

    return templates.TemplateResponse(request, "fisico/planeamento.html", {
        "utilizador": utilizador,
        "equipa": equipa,
        "planeamentos": planeamentos,
        "jogadores": jogadores,
        "testes": testes,
        "tipos_testes": tipos_testes,
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
    unidade = str(form.get("unidade") or "").strip() or None
    observacoes = str(form.get("observacoes") or "").strip() or None
    try:
        jogadores_ids = {int(valor) for valor in form.getlist("jogador_ids")}
    except (TypeError, ValueError):
        jogadores_ids = set()
    if not tipo_teste or not jogadores_ids:
        set_flash(request, "Indica o tipo de teste e seleciona pelo menos um atleta.", "erro")
        return RedirectResponse(url=f"/fisico/equipas/{equipa_id}#testes-fisicos", status_code=303)

    jogadores = db.query(Jogador).filter(
        Jogador.equipa_id == equipa_id,
        Jogador.id.in_(jogadores_ids),
        Jogador.ativo.is_(True),
    ).all()
    if len(jogadores) != len(jogadores_ids):
        set_flash(request, "Existe um atleta inválido na seleção.", "erro")
        return RedirectResponse(url=f"/fisico/equipas/{equipa_id}#testes-fisicos", status_code=303)

    novos_testes = []
    try:
        for jogador in jogadores:
            novos_testes.append(TesteFisico(
                clube_id=equipa.clube_id,
                jogador_id=jogador.id,
                data=data_teste,
                tipo_teste=tipo_teste,
                resultado=_resultado_numerico(str(form.get(f"resultado_{jogador.id}") or "")),
                unidade=unidade,
                observacoes=observacoes,
            ))
    except ValueError:
        set_flash(request, "Os resultados devem ser valores numéricos.", "erro")
        return RedirectResponse(url=f"/fisico/equipas/{equipa_id}#testes-fisicos", status_code=303)

    db.add_all(novos_testes)
    db.commit()
    set_flash(request, f"Teste físico registado para {len(novos_testes)} atleta(s).")
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

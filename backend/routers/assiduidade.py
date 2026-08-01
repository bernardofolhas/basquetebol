from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from template_config import Jinja2Templates
from sqlalchemy.orm import Session

from auth_deps import AcessoNegado, exigir_autenticacao, verificar_ou_negar_equipa
from database import get_db
from flash import set_flash
from models.assiduidade import RegistoAssiduidade
from models.equipa import Equipa
from models.jogador import Jogador
from models.planeamento import SessaoTreino
from paths import TEMPLATES_DIR
from services.sincronizacao_ui import enriquecer_sessao_para_ui
from services.pdf_service import renderizar_pdf
from services.assiduidade_service import (
    ESTADOS_ASSIDUIDADE,
    ESTADOS_ASSIDUIDADE_VISUAL,
    calcular_resumo_assiduidade,
    estado_assiduidade_visual,
    estado_para_presenca,
    normalizar_estado_assiduidade,
    obter_relatorio_assiduidade_equipa,
)
from services.sessao_workflow import normalizar_estado_sessao

router = APIRouter(prefix="/assiduidade")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _data_query(valor: str | None) -> date | None:
    try:
        return date.fromisoformat(valor) if valor else None
    except ValueError:
        return None


def _contexto_relatorio_equipa(request: Request, equipa, relatorio: dict, utilizador) -> dict:
    return {
        "utilizador": utilizador,
        "equipa": equipa,
        **relatorio,
        "estados_assiduidade": ESTADOS_ASSIDUIDADE,
        "estados_assiduidade_visual": ESTADOS_ASSIDUIDADE_VISUAL,
        "request": request,
    }


@router.get("/equipas/{equipa_id}", response_class=HTMLResponse)
def relatorio_assiduidade_equipa(
    equipa_id: int,
    request: Request,
    inicio: str = "",
    fim: str = "",
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    verificar_ou_negar_equipa(utilizador, equipa_id, db)
    equipa = db.query(Equipa).filter(Equipa.id == equipa_id).first()
    if not equipa:
        return RedirectResponse(url="/equipas")

    relatorio = obter_relatorio_assiduidade_equipa(
        db,
        equipa_id,
        _data_query(inicio),
        _data_query(fim),
    )
    return templates.TemplateResponse(
        request,
        "assiduidade/equipa.html",
        _contexto_relatorio_equipa(request, equipa, relatorio, utilizador),
    )


@router.get("/equipas/{equipa_id}/pdf")
def exportar_pdf_assiduidade_equipa(
    equipa_id: int,
    request: Request,
    inicio: str = "",
    fim: str = "",
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    verificar_ou_negar_equipa(utilizador, equipa_id, db)
    equipa = db.query(Equipa).filter(Equipa.id == equipa_id).first()
    if not equipa:
        return RedirectResponse(url="/equipas")

    relatorio = obter_relatorio_assiduidade_equipa(
        db,
        equipa_id,
        _data_query(inicio),
        _data_query(fim),
    )
    contexto = _contexto_relatorio_equipa(request, equipa, relatorio, utilizador)
    pdf_bytes = renderizar_pdf(request, "assiduidade/equipa_pdf.html", contexto)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=assiduidade_{equipa.id}.pdf"},
    )


@router.get("/sessoes/{sessao_id}", response_class=HTMLResponse)
def pagina_assiduidade(
    sessao_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    sessao = db.query(SessaoTreino).filter(SessaoTreino.id == sessao_id).first()
    if not sessao:
        return RedirectResponse(url="/equipas")
    sessao = enriquecer_sessao_para_ui(sessao)

    equipa = sessao.microciclo.mesociclo.macrociclo.equipa
    verificar_ou_negar_equipa(utilizador, equipa.id, db)

    jogadores = db.query(Jogador).filter(
        Jogador.equipa_id == equipa.id
    ).order_by(Jogador.nome).all()

    registos_existentes = db.query(RegistoAssiduidade).filter(
        RegistoAssiduidade.sessao_id == sessao_id
    ).all()

    registos = db.query(RegistoAssiduidade).filter(
        RegistoAssiduidade.sessao_id == sessao_id
    ).all()
    registos_dict = {r.jogador_id: r for r in registos}

    resumo = calcular_resumo_assiduidade(registos)
    resumo["registados"] = len(registos)
    resumo["por_registar"] = max(len(jogadores) - len(registos), 0)
    resumo["por_estado"]["por_registar"] = resumo["por_registar"]
    resumo["percentagem_esperada"] = round(
        (resumo["presentes"] / len(jogadores)) * 100,
        1,
    ) if jogadores else 0
    for registo in registos:
        registo.estado_visual = estado_assiduidade_visual(registo.estado, registo.presente)

    return templates.TemplateResponse(request, "assiduidade/sessao.html", {
        "utilizador": utilizador,
        "sessao": sessao,
        "equipa": equipa,
        "jogadores": jogadores,
        "registos_dict": registos_dict,
        "total_presentes": resumo["presentes"],
        "total_jogadores": len(jogadores),
        "percentagem": resumo["percentagem"],
        "resumo_assiduidade": resumo,
        "estados_assiduidade": ESTADOS_ASSIDUIDADE,
        "estados_assiduidade_visual": ESTADOS_ASSIDUIDADE_VISUAL,
    })


@router.post("/sessoes/{sessao_id}")
async def guardar_assiduidade(
    sessao_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    sessao_check = db.query(SessaoTreino).filter(SessaoTreino.id == sessao_id).first()
    if sessao_check:
        equipa_check = sessao_check.microciclo.mesociclo.macrociclo.equipa
        verificar_ou_negar_equipa(utilizador, equipa_check.id, db)

    dados = await request.form()

    registos = db.query(RegistoAssiduidade).filter(
        RegistoAssiduidade.sessao_id == sessao_id
    ).all()
    registos_por_jogador = {registo.jogador_id: registo for registo in registos}
    jogadores = []
    if sessao_check:
        equipa = sessao_check.microciclo.mesociclo.macrociclo.equipa
        jogadores = db.query(Jogador).filter(Jogador.equipa_id == equipa.id).all()

    for jogador in jogadores:
        registo = registos_por_jogador.get(jogador.id)
        if not registo:
            registo = RegistoAssiduidade(
                sessao_id=sessao_id,
                jogador_id=jogador.id,
            )
            db.add(registo)
        estado_form = dados.get(f"estado_{jogador.id}")
        checkbox_presente = dados.get(f"presente_{jogador.id}") == "on"
        estado = normalizar_estado_assiduidade(estado_form, checkbox_presente)
        motivo = dados.get(f"motivo_{jogador.id}", "")
        registo.estado = estado
        registo.presente = estado_para_presenca(estado)
        registo.motivo_falta = motivo if not registo.presente and motivo else None

    if sessao_check and normalizar_estado_sessao(sessao_check.estado) == "executada" and all(
        normalizar_estado_assiduidade(
            dados.get(f"estado_{jogador.id}"),
            dados.get(f"presente_{jogador.id}") == "on",
        ) != "por_registar"
        for jogador in jogadores
    ):
        sessao_check.estado = "registada"
    db.commit()
    set_flash(request, "Assiduidade guardada com sucesso.")
    return RedirectResponse(url=f"/assiduidade/sessoes/{sessao_id}", status_code=303)

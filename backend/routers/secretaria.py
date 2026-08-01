from datetime import date, timedelta

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from template_config import Jinja2Templates
from sqlalchemy.orm import Session, joinedload

from auth_deps import exigir_secretaria
from database import get_db
from flash import set_flash
from models.documento_jogador import DocumentoJogador
from models.jogador import Jogador
from paths import TEMPLATES_DIR
from services.auditoria_service import registar_auditoria
from services.pdf_service import renderizar_pdf

router = APIRouter(prefix="/secretaria")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
ESTADOS_DOCUMENTO = ("pendente", "válido", "expirado", "dispensado")


def _obter_pendencias(db: Session) -> dict:
    hoje = date.today()
    limite = hoje + timedelta(days=30)
    jogadores = db.query(Jogador).options(
        joinedload(Jogador.equipa),
        joinedload(Jogador.documentos),
    ).order_by(Jogador.nome).all()
    linhas = []
    total_documentos = 0
    for jogador in jogadores:
        pendencias = []
        if jogador.inscricao_estado != "completa":
            pendencias.append("Inscrição por completar")
        if not jogador.exame_medico_validade:
            pendencias.append("Exame médico sem validade")
        elif jogador.exame_medico_validade <= limite:
            pendencias.append(
                "Exame médico expirado" if jogador.exame_medico_validade < hoje else "Exame médico a expirar"
            )
        documentos = list(jogador.documentos or [])
        total_documentos += len(documentos)
        for documento in documentos:
            if documento.estado in {"pendente", "expirado"}:
                pendencias.append(f"{documento.nome}: {documento.estado}")
            elif documento.validade and documento.validade <= limite:
                pendencias.append(
                    f"{documento.nome}: " + ("expirado" if documento.validade < hoje else "a expirar")
                )
        if pendencias:
            linhas.append({"jogador": jogador, "pendencias": pendencias})
    return {
        "linhas": linhas,
        "total_jogadores": len(jogadores),
        "total_pendencias": sum(len(linha["pendencias"]) for linha in linhas),
        "total_documentos": total_documentos,
        "hoje": hoje,
        "limite": limite,
    }


@router.get("/pendencias", response_class=HTMLResponse)
def pagina_pendencias(
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_secretaria),
):
    return templates.TemplateResponse(request, "secretaria/pendencias.html", {
        "utilizador": utilizador,
        **_obter_pendencias(db),
    })


@router.get("/pendencias/pdf")
def exportar_pendencias_pdf(
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_secretaria),
):
    contexto = {"utilizador": utilizador, **_obter_pendencias(db)}
    pdf = renderizar_pdf(request, "secretaria/pendencias_pdf.html", contexto)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=pendencias_secretaria.pdf"},
    )


@router.post("/jogadores/{jogador_id}/documentos")
def criar_documento_jogador(
    jogador_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_secretaria),
    tipo: str = Form(...),
    nome: str = Form(...),
    data_documento: str = Form(""),
    validade: str = Form(""),
    estado: str = Form("pendente"),
    observacoes: str = Form(""),
):
    jogador = db.query(Jogador).filter(Jogador.id == jogador_id).first()
    if not jogador:
        return RedirectResponse(url="/jogadores", status_code=303)
    tipo = tipo.strip()
    nome = nome.strip()
    if not tipo or not nome:
        set_flash(request, "Indica o tipo e o nome do documento.", "error")
        return RedirectResponse(url=f"/jogadores/{jogador_id}", status_code=303)
    if estado not in ESTADOS_DOCUMENTO:
        estado = "pendente"
    try:
        data_documento_convertida = date.fromisoformat(data_documento) if data_documento else None
        validade_convertida = date.fromisoformat(validade) if validade else None
    except ValueError:
        set_flash(request, "As datas do documento não são válidas.", "error")
        return RedirectResponse(url=f"/jogadores/{jogador_id}", status_code=303)
    documento = DocumentoJogador(
        jogador_id=jogador_id,
        tipo=tipo,
        nome=nome,
        data_documento=data_documento_convertida,
        validade=validade_convertida,
        estado=estado,
        observacoes=observacoes.strip() or None,
    )
    db.add(documento)
    registar_auditoria(db, utilizador, "criar", "documento_jogador", jogador_id, f"Documento: {nome}", request)
    db.commit()
    set_flash(request, "Documento adicionado ao processo da jogadora.")
    return RedirectResponse(url=f"/jogadores/{jogador_id}", status_code=303)


@router.post("/documentos/{documento_id}/apagar")
def apagar_documento_jogador(
    documento_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_secretaria),
):
    documento = db.query(DocumentoJogador).filter(DocumentoJogador.id == documento_id).first()
    if documento:
        jogador_id = documento.jogador_id
        registar_auditoria(db, utilizador, "apagar", "documento_jogador", jogador_id, documento.nome, request)
        db.delete(documento)
        db.commit()
        set_flash(request, "Documento removido.")
        return RedirectResponse(url=f"/jogadores/{jogador_id}", status_code=303)
    return RedirectResponse(url="/secretaria/pendencias", status_code=303)

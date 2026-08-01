# ─────────────────────────────────────────────────────────────
# ROUTER DE PLANO DE TREINO
# Gere a criação e edição de planos de treino detalhados
# Cada sessão de treino pode ter um plano com vários exercícios
# organizados em blocos (A, B, C, D)
# ─────────────────────────────────────────────────────────────

from fastapi import APIRouter, Request, Depends, Form
from template_config import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse, Response, JSONResponse
from sqlalchemy.orm import Session

from auth import verificar_acesso_equipa
from auth_deps import AcessoNegado, exigir_autenticacao
from database import get_db
from flash import set_flash
from horarios import hora_eh_anterior, hora_valida, normalizar_hora
from models.espaco_agenda import AgendaEspacoEquipa
from models.planeamento import SessaoTreino
from models.treino import BibliotecoExercicio, BlocoTreino, ExercicioPlano, PlanoTreino
from paths import STATIC_DIR, TEMPLATES_DIR
from services.desenho_service import (
    compor_desenho_sobre_campo,
    imagem_estatica_data_uri,
    normalizar_data_uri,
)
from services.sincronizacao_ui import enriquecer_sessao_para_ui
from services.pdf_service import renderizar_pdf
from services.sessao_workflow import (
    ESTADOS_SESSAO,
    normalizar_estado_sessao,
    opcoes_transicao_sessao,
    transicao_sessao_valida,
)

router = APIRouter(prefix="/treino")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

TIPOS_CAMPO = {
    1: ("meio", "Campo meio", "campo_meio.png"),
    2: ("completo", "Campo completo", "campo_completo.png"),
    3: ("meio", "Campo meio extra", "campo_meio.png"),
    4: ("completo", "Campo completo extra", "campo_completo.png"),
}


def _slots_ativos(exercicio: ExercicioPlano) -> list[int]:
    valor = exercicio.campos_ativos
    if valor is None:
        return [1, 2] + [numero for numero in (3, 4) if getattr(exercicio, f"desenho_{numero}", None)]
    return [int(item) for item in valor.split(",") if item.isdigit() and int(item) in TIPOS_CAMPO]


def _definir_slots_ativos(exercicio: ExercicioPlano, slots: list[int]) -> None:
    exercicio.campos_ativos = ",".join(str(numero) for numero in TIPOS_CAMPO if numero in slots)


def _campos_exercicio(exercicio: ExercicioPlano) -> list[dict]:
    return [
        {
            "numero": numero,
            "tipo": TIPOS_CAMPO[numero][0],
            "label": TIPOS_CAMPO[numero][1],
            "imagem": TIPOS_CAMPO[numero][2],
            "desenho": getattr(exercicio, f"desenho_{numero}"),
        }
        for numero in _slots_ativos(exercicio)
    ]


def _reordenar_exercicios_bloco(db: Session, plano_id: int, bloco: str) -> None:
    """Mantém a ordenação sequencial dos exercícios dentro de cada bloco."""
    exercicios = (
        db.query(ExercicioPlano)
        .filter(
            ExercicioPlano.plano_id == plano_id,
            ExercicioPlano.bloco == bloco,
        )
        .order_by(ExercicioPlano.ordem.asc(), ExercicioPlano.id.asc())
        .all()
    )
    for indice, exercicio in enumerate(exercicios, start=1):
        exercicio.ordem = indice


def _reordenar_blocos(db: Session, plano_id: int) -> None:
    blocos = db.query(BlocoTreino).filter(BlocoTreino.plano_id == plano_id).order_by(BlocoTreino.ordem, BlocoTreino.id).all()
    for indice, bloco in enumerate(blocos, 1):
        bloco.ordem = indice


def _construir_resumo_blocos(plano: PlanoTreino | None) -> list[dict]:
    """Resume o conteúdo de cada bloco para o cabeçalho da ficha."""
    resumo = []
    exercicios = list(plano.exercicios or []) if plano else []
    blocos = list(plano.blocos or []) if plano else []
    for bloco_dinamico in blocos:
        exercicios_bloco = [ex for ex in exercicios if ex.bloco_id == bloco_dinamico.id]
        resumo.append({
            "bloco": bloco_dinamico.nome,
            "bloco_id": bloco_dinamico.id,
            "total": len(exercicios_bloco),
            "minutos": sum(ex.minutos or 0 for ex in exercicios_bloco),
            "categorias": sorted({ex.categoria for ex in exercicios_bloco if ex.categoria}),
        })
    for bloco in ["A", "B", "C", "D"]:
        exercicios_bloco = [ex for ex in exercicios if not ex.bloco_id and (ex.bloco or "A") == bloco]
        if exercicios_bloco:
            resumo.append({"bloco": bloco, "bloco_id": None, "total": len(exercicios_bloco), "minutos": sum(ex.minutos or 0 for ex in exercicios_bloco), "categorias": sorted({ex.categoria for ex in exercicios_bloco if ex.categoria})})
    return resumo


def _contexto_impressao_plano(request, sessao, equipa, plano, utilizador) -> dict:
    """Prepara uma ficha estável para HTML de impressão e WeasyPrint."""
    caminho_campo_meio = STATIC_DIR / "campos" / "campo_meio.png"
    caminho_campo_completo = STATIC_DIR / "campos" / "campo_completo.png"
    exercicios_por_bloco = {f"d{bloco.id}": [] for bloco in plano.blocos} if plano else {}
    exercicios = list(plano.exercicios or []) if plano else []
    nome_treinador = getattr(getattr(utilizador, "treinador", None), "nome", None)
    if not nome_treinador and getattr(equipa, "treinadores", None):
        nome_treinador = equipa.treinadores[0].nome
    for exercicio in exercicios:
        bloco = f"d{exercicio.bloco_id}" if exercicio.bloco_id else (exercicio.bloco or "A")
        if bloco not in exercicios_por_bloco and not exercicio.bloco_id:
            exercicios_por_bloco[bloco] = []
        if bloco in exercicios_por_bloco:
            campos_pdf = []
            for campo in _campos_exercicio(exercicio):
                caminho = caminho_campo_meio if campo["tipo"] == "meio" else caminho_campo_completo
                campos_pdf.append({
                    **campo,
                    "imagem_composta": compor_desenho_sobre_campo(caminho, campo["desenho"]),
                })
            setattr(exercicio, "campos_pdf", campos_pdf)
            exercicios_por_bloco[bloco].append(exercicio)

    return {
        "utilizador": utilizador,
        "sessao": sessao,
        "equipa": equipa,
        "plano": plano,
        "exercicios_por_bloco": exercicios_por_bloco,
        "resumo_blocos": _construir_resumo_blocos(plano),
        "blocos_ui": ([{"key": f"d{bloco.id}", "id": bloco.id, "nome": bloco.nome, "tipo": bloco.tipo, "legado": False} for bloco in plano.blocos] if plano else []) + [{"key": letra, "id": None, "nome": f"Bloco {letra}", "tipo": "Legado", "legado": True} for letra in ["A", "B", "C", "D"] if letra in exercicios_por_bloco],
        "total_exercicios": len(exercicios),
        "volume_planeado": sum(ex.minutos or 0 for ex in exercicios),
        "rpe_geral": sessao.intensidade_rpe,
        "campo_meio_data_uri": imagem_estatica_data_uri(caminho_campo_meio),
        "campo_completo_data_uri": imagem_estatica_data_uri(caminho_campo_completo),
        "identidade": getattr(request.state, "identidade_clube", {}),
        "nome_treinador": nome_treinador or utilizador.nome,
    }


def _obter_equipa_id_por_sessao(db: Session, sessao_id: int) -> int | None:
    """Resolve a equipa associada a uma sessão de treino."""
    sessao = db.query(SessaoTreino).filter(SessaoTreino.id == sessao_id).first()
    if not sessao or not sessao.microciclo or not sessao.microciclo.mesociclo or not sessao.microciclo.mesociclo.macrociclo:
        return None
    return sessao.microciclo.mesociclo.macrociclo.equipa_id


def _obter_equipa_id_por_plano(db: Session, plano_id: int) -> int | None:
    """Resolve a equipa associada a um plano de treino."""
    plano = db.query(PlanoTreino).filter(PlanoTreino.id == plano_id).first()
    if not plano:
        return None
    return _obter_equipa_id_por_sessao(db, plano.sessao_id)


def _obter_equipa_id_por_exercicio(db: Session, exercicio_id: int) -> int | None:
    """Resolve a equipa associada a um exercício do plano."""
    exercicio = db.query(ExercicioPlano).filter(ExercicioPlano.id == exercicio_id).first()
    if not exercicio:
        return None
    return _obter_equipa_id_por_plano(db, exercicio.plano_id)


def _verificar_acesso_treino(utilizador, equipa_id: int | None, db: Session) -> None:
    """Valida se o utilizador pode aceder ao treino; lança AcessoNegado se não."""
    if not equipa_id or not verificar_acesso_equipa(utilizador, equipa_id, db):
        raise AcessoNegado("/equipas")


def _marcar_sessao_como_alterada_manual(sessao: SessaoTreino | None):
    """Assinala que a sessão originada do planeamento global foi mexida manualmente."""
    if not sessao or sessao.origem != "planeamento_global":
        return
    sessao.alterada_manual = True
    sessao.sincronizada = False


def _validar_intervalo_horario(hora_inicio: str | None, hora_fim: str | None) -> str | None:
    """Garante coerência mínima no horário da sessão."""
    if not hora_valida(hora_inicio) or not hora_valida(hora_fim):
        return "As horas do treino devem estar no formato HH:MM."
    hora_inicio_normalizada = normalizar_hora(hora_inicio)
    hora_fim_normalizada = normalizar_hora(hora_fim)
    if hora_inicio_normalizada and hora_fim_normalizada and not hora_eh_anterior(
        hora_inicio_normalizada,
        hora_fim_normalizada,
    ):
        return "A hora de início tem de ser anterior à hora de término."
    return None


def _normalizar_rpe(valor: str | None) -> float | None:
    """Converte e valida um RPE numa escala de 1 a 10."""
    if not valor or not valor.strip():
        return None
    try:
        rpe = float(valor.replace(",", "."))
    except ValueError:
        raise ValueError("O RPE deve ser um número entre 1 e 10.")
    if not 1 <= rpe <= 10:
        raise ValueError("O RPE deve estar entre 1 e 10.")
    return rpe


def _normalizar_minutos(valor: str | None) -> int | None:
    """Converte a duração de um exercício e evita erros 500 em formulários manuais."""
    if not valor or not valor.strip():
        return None
    try:
        minutos = int(valor)
    except (TypeError, ValueError) as erro:
        raise ValueError("Os minutos devem ser um número inteiro entre 1 e 240.") from erro
    if not 1 <= minutos <= 240:
        raise ValueError("Os minutos devem estar entre 1 e 240.")
    return minutos


def _duracao_prevista_minutos(sessao: SessaoTreino) -> int | None:
    if not sessao.hora_inicio or not sessao.hora_fim:
        return None
    try:
        inicio_h, inicio_m = map(int, sessao.hora_inicio.split(":"))
        fim_h, fim_m = map(int, sessao.hora_fim.split(":"))
    except (TypeError, ValueError):
        return None
    duracao = (fim_h * 60 + fim_m) - (inicio_h * 60 + inicio_m)
    return duracao if duracao > 0 else None


def _normalizar_bloco(bloco: str | None) -> str:
    valor = (bloco or "A").strip().upper()
    if valor not in {"A", "B", "C", "D"}:
        raise ValueError("O bloco do exercício deve ser A, B, C ou D.")
    return valor


# ─────────────────────────────────────────
# PÁGINA DO PLANO DE TREINO DE UMA SESSÃO
# URL: GET /treino/sessoes/{sessao_id}
# ─────────────────────────────────────────
@router.get("/sessoes/{sessao_id}", response_class=HTMLResponse)
def pagina_plano_treino(sessao_id: int, request: Request, db: Session = Depends(get_db),
                        utilizador=Depends(exigir_autenticacao)):
    _verificar_acesso_treino(utilizador, _obter_equipa_id_por_sessao(db, sessao_id), db)

    sessao = db.query(SessaoTreino).filter(SessaoTreino.id == sessao_id).first()
    if not sessao:
        return RedirectResponse(url="/equipas")
    sessao = enriquecer_sessao_para_ui(sessao)

    equipa = sessao.microciclo.mesociclo.macrociclo.equipa

    plano = db.query(PlanoTreino).filter(PlanoTreino.sessao_id == sessao_id).first()

    if not plano:
        plano = PlanoTreino(sessao_id=sessao_id)
        db.add(plano)
        db.commit()
        db.refresh(plano)

    exercicios_por_bloco = {f"d{bloco.id}": [] for bloco in plano.blocos}
    for ex in plano.exercicios:
        setattr(ex, "campos_ui", _campos_exercicio(ex))
        bloco = f"d{ex.bloco_id}" if ex.bloco_id else (ex.bloco or "A")
        exercicios_por_bloco.setdefault(bloco, []).append(ex)

    espacos_disponiveis = (
        db.query(AgendaEspacoEquipa)
        .filter(
            AgendaEspacoEquipa.equipa_id == equipa.id,
            AgendaEspacoEquipa.data == sessao.data,
            AgendaEspacoEquipa.ativo == True,
        )
        .order_by(AgendaEspacoEquipa.hora_inicio)
        .all()
    )

    volume_planeado = sum(ex.minutos or 0 for ex in plano.exercicios)
    duracao_prevista = _duracao_prevista_minutos(sessao)
    return templates.TemplateResponse(request, "treino/plano.html", {
        "utilizador": utilizador,
        "sessao": sessao,
        "equipa": equipa,
        "plano": plano,
        "exercicios_por_bloco": exercicios_por_bloco,
        "espacos_disponiveis": espacos_disponiveis,
        "categorias_exercicio": ["TIO", "TID", "TaIO", "TaID", "TCO", "TCD", "FIS"],
        "resumo_blocos": _construir_resumo_blocos(plano),
        "blocos_ui": [{"key": f"d{bloco.id}", "id": bloco.id, "nome": bloco.nome, "tipo": bloco.tipo, "legado": False} for bloco in plano.blocos] + [{"key": letra, "id": None, "nome": f"Bloco {letra}", "tipo": "Legado", "legado": True} for letra in ["A", "B", "C", "D"] if letra in exercicios_por_bloco],
        "total_exercicios": len(plano.exercicios),
        "volume_planeado": volume_planeado,
        "duracao_prevista": duracao_prevista,
        "diferenca_duracao": volume_planeado - duracao_prevista if duracao_prevista is not None else None,
        "estados_sessao": opcoes_transicao_sessao(sessao.estado),
    })


@router.post("/sessoes/{sessao_id}/estado")
async def atualizar_estado_sessao(
    sessao_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
    estado: str = Form(...),
):
    """Avança ou reabre uma sessão dentro do fluxo operacional permitido."""
    equipa_id = _obter_equipa_id_por_sessao(db, sessao_id)
    _verificar_acesso_treino(utilizador, equipa_id, db)
    sessao = db.query(SessaoTreino).filter(SessaoTreino.id == sessao_id).first()
    if not sessao:
        return RedirectResponse(url="/equipas", status_code=303)

    novo_estado = (estado or "").strip().lower()
    estado_atual = normalizar_estado_sessao(getattr(sessao, "estado", None))
    if novo_estado not in ESTADOS_SESSAO:
        set_flash(request, "Estado da sessão inválido.", "error")
        return RedirectResponse(url=f"/treino/sessoes/{sessao_id}", status_code=303)
    if novo_estado != estado_atual and not transicao_sessao_valida(estado_atual, novo_estado):
        set_flash(
            request,
            f"Não é possível passar diretamente de {estado_atual} para {novo_estado}.",
            "error",
        )
        return RedirectResponse(url=f"/treino/sessoes/{sessao_id}", status_code=303)

    sessao.estado = novo_estado
    db.commit()
    set_flash(request, "Estado da sessão atualizado.")
    return RedirectResponse(url=f"/treino/sessoes/{sessao_id}", status_code=303)


# ─────────────────────────────────────────
# GUARDAR CABEÇALHO DO PLANO
# URL: POST /treino/planos/{plano_id}/cabecalho
# ─────────────────────────────────────────
@router.post("/planos/{plano_id}/cabecalho")
async def guardar_cabecalho(
    plano_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
    hora_inicio: str = Form(""),
    hora_fim: str = Form(""),
    local: str = Form(""),
    escalao: str = Form(""),
    objectivos: str = Form(""),
    intensidade_rpe: str = Form(""),
):
    _verificar_acesso_treino(utilizador, _obter_equipa_id_por_plano(db, plano_id), db)

    plano = db.query(PlanoTreino).filter(PlanoTreino.id == plano_id).first()
    if plano:
        erro_horario = _validar_intervalo_horario(hora_inicio or None, hora_fim or None)
        if erro_horario:
            set_flash(request, erro_horario, "error")
            return RedirectResponse(url=f"/treino/sessoes/{plano.sessao_id}", status_code=303)
        try:
            rpe_geral = _normalizar_rpe(intensidade_rpe)
        except ValueError as erro:
            set_flash(request, str(erro), "error")
            return RedirectResponse(url=f"/treino/sessoes/{plano.sessao_id}", status_code=303)
        hora_inicio = normalizar_hora(hora_inicio)
        hora_fim = normalizar_hora(hora_fim)

        _marcar_sessao_como_alterada_manual(plano.sessao)
        plano.hora_inicio = hora_inicio
        plano.escalao = escalao or None
        plano.objectivos = objectivos or None
        if plano.sessao:
            plano.sessao.local = local or None
            plano.sessao.hora_inicio = hora_inicio
            plano.sessao.hora_fim = hora_fim
            plano.sessao.intensidade_rpe = rpe_geral
        db.commit()

    return RedirectResponse(url=f"/treino/sessoes/{plano.sessao_id}", status_code=303)


@router.post("/planos/{plano_id}/blocos")
async def criar_bloco(plano_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_autenticacao), nome: str = Form(...), tipo: str = Form("")):
    _verificar_acesso_treino(utilizador, _obter_equipa_id_por_plano(db, plano_id), db)
    plano = db.query(PlanoTreino).filter(PlanoTreino.id == plano_id).first()
    if not plano or not nome.strip():
        set_flash(request, "Indica um nome para o bloco.", "error")
        return RedirectResponse(url=f"/treino/sessoes/{plano.sessao_id if plano else ''}", status_code=303)
    db.add(BlocoTreino(plano_id=plano.id, nome=nome.strip(), tipo=tipo.strip() or None, ordem=len(plano.blocos) + 1))
    _marcar_sessao_como_alterada_manual(plano.sessao)
    db.commit()
    set_flash(request, "Bloco criado. Já podes adicionar exercícios.")
    return RedirectResponse(url=f"/treino/sessoes/{plano.sessao_id}", status_code=303)


@router.post("/blocos/{bloco_id}/editar")
async def editar_bloco(bloco_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_autenticacao), nome: str = Form(...), tipo: str = Form(""), ordem: int = Form(1)):
    bloco = db.query(BlocoTreino).filter(BlocoTreino.id == bloco_id).first()
    if not bloco:
        return RedirectResponse(url="/equipas", status_code=303)
    _verificar_acesso_treino(utilizador, _obter_equipa_id_por_plano(db, bloco.plano_id), db)
    bloco.nome, bloco.tipo, bloco.ordem = nome.strip() or bloco.nome, tipo.strip() or None, max(1, ordem)
    _reordenar_blocos(db, bloco.plano_id)
    db.commit()
    set_flash(request, "Bloco atualizado.")
    return RedirectResponse(url=f"/treino/sessoes/{bloco.plano.sessao_id}", status_code=303)


@router.post("/blocos/{bloco_id}/duplicar")
async def duplicar_bloco(bloco_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_autenticacao)):
    bloco = db.query(BlocoTreino).filter(BlocoTreino.id == bloco_id).first()
    if not bloco:
        return RedirectResponse(url="/equipas", status_code=303)
    _verificar_acesso_treino(utilizador, _obter_equipa_id_por_plano(db, bloco.plano_id), db)
    copia = BlocoTreino(plano_id=bloco.plano_id, nome=f"{bloco.nome} (cópia)", tipo=bloco.tipo, ordem=len(bloco.plano.blocos) + 1)
    db.add(copia); db.flush()
    for ex in bloco.exercicios:
        db.add(ExercicioPlano(plano_id=ex.plano_id, bloco_id=copia.id, ordem=ex.ordem, hora=ex.hora, minutos=ex.minutos, rpe=ex.rpe, nome=ex.nome, categoria=ex.categoria, desenho_1=ex.desenho_1, desenho_2=ex.desenho_2, desenho_3=ex.desenho_3, desenho_4=ex.desenho_4, campos_ativos=ex.campos_ativos, organizacao=ex.organizacao, coaching_points=ex.coaching_points))
    db.commit(); set_flash(request, "Bloco e exercícios duplicados.")
    return RedirectResponse(url=f"/treino/sessoes/{bloco.plano.sessao_id}", status_code=303)


@router.post("/blocos/{bloco_id}/apagar")
async def apagar_bloco(bloco_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_autenticacao)):
    bloco = db.query(BlocoTreino).filter(BlocoTreino.id == bloco_id).first()
    if not bloco:
        return RedirectResponse(url="/equipas", status_code=303)
    _verificar_acesso_treino(utilizador, _obter_equipa_id_por_plano(db, bloco.plano_id), db)
    if bloco.exercicios:
        set_flash(request, "Remove ou desloca os exercícios antes de apagar o bloco.", "error")
    else:
        plano_id, sessao_id = bloco.plano_id, bloco.plano.sessao_id
        db.delete(bloco); db.flush(); _reordenar_blocos(db, plano_id); db.commit(); set_flash(request, "Bloco removido.")
        return RedirectResponse(url=f"/treino/sessoes/{sessao_id}", status_code=303)
    return RedirectResponse(url=f"/treino/sessoes/{bloco.plano.sessao_id}", status_code=303)


# ─────────────────────────────────────────
# ADICIONAR EXERCÍCIO A UM BLOCO
# URL: POST /treino/planos/{plano_id}/exercicios
# ─────────────────────────────────────────
@router.post("/planos/{plano_id}/exercicios")
async def adicionar_exercicio(
    plano_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
    bloco: str = Form("A"),
    bloco_id: str = Form(""),
    nome: str = Form(""),
    categoria: str = Form(""),
    hora: str = Form(""),
    minutos: str = Form(""),
    rpe: str = Form(""),
    organizacao: str = Form(""),
    coaching_points: str = Form(""),
    biblioteca_id: str = Form("")
):
    _verificar_acesso_treino(utilizador, _obter_equipa_id_por_plano(db, plano_id), db)
    plano = db.query(PlanoTreino).filter(PlanoTreino.id == plano_id).first()
    if not plano:
        return RedirectResponse(url="/equipas", status_code=303)

    try:
        rpe_exercicio = _normalizar_rpe(rpe)
        minutos_exercicio = _normalizar_minutos(minutos)
        bloco_dinamico_id = int(bloco_id) if bloco_id else None
        bloco = _normalizar_bloco(bloco) if not bloco_dinamico_id else None
    except ValueError as erro:
        set_flash(request, str(erro), "error")
        return RedirectResponse(url=f"/treino/sessoes/{plano.sessao_id}", status_code=303)

    total_no_bloco = db.query(ExercicioPlano).filter(
        ExercicioPlano.plano_id == plano_id,
        ExercicioPlano.bloco_id == bloco_dinamico_id if bloco_dinamico_id else ExercicioPlano.bloco == bloco
    ).count()

    biblioteca = None
    if biblioteca_id:
        try:
            biblioteca = db.query(BibliotecoExercicio).filter(
                BibliotecoExercicio.id == int(biblioteca_id)
            ).first()
        except ValueError:
            biblioteca = None

    if biblioteca:
        nome = nome or biblioteca.nome
        categoria = categoria or biblioteca.categoria or ""
        organizacao = organizacao or biblioteca.organizacao or ""
        coaching_points = coaching_points or biblioteca.coaching_points or ""

    exercicio = ExercicioPlano(
        plano_id=plano_id,
        bloco=bloco,
        bloco_id=bloco_dinamico_id,
        ordem=total_no_bloco + 1,
        nome=nome or None,
        categoria=categoria or None,
        hora=hora or None,
        minutos=minutos_exercicio,
        rpe=rpe_exercicio,
        organizacao=organizacao or None,
        coaching_points=coaching_points or None
    )
    if biblioteca and biblioteca.desenho:
        exercicio.desenho_1 = biblioteca.desenho
    if biblioteca and biblioteca.desenho_campo_completo:
        exercicio.desenho_2 = biblioteca.desenho_campo_completo

    _marcar_sessao_como_alterada_manual(plano.sessao if plano else None)
    db.add(exercicio)

    nome_norm = nome.strip() if nome else None
    if nome_norm:
        existente = db.query(BibliotecoExercicio).filter(
            BibliotecoExercicio.nome.ilike(nome_norm)
        ).first()
        if not existente:
            db.add(BibliotecoExercicio(
                nome=nome_norm,
                categoria=categoria or None,
                organizacao=organizacao or None,
                coaching_points=coaching_points or None,
            ))

    db.commit()

    return RedirectResponse(url=f"/treino/sessoes/{plano.sessao_id}", status_code=303)


@router.post("/planos/{plano_id}/biblioteca/{biblioteca_id}")
async def adicionar_exercicio_da_biblioteca(
    plano_id: int,
    biblioteca_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
    bloco: str = Form("A"),
    minutos: str = Form(""),
    hora: str = Form(""),
    rpe: str = Form(""),
):
    """Cria uma cópia editável de um exercício da biblioteca no plano."""
    _verificar_acesso_treino(utilizador, _obter_equipa_id_por_plano(db, plano_id), db)
    plano = db.query(PlanoTreino).filter(PlanoTreino.id == plano_id).first()
    biblioteca = db.query(BibliotecoExercicio).filter(BibliotecoExercicio.id == biblioteca_id).first()
    if not plano or not biblioteca:
        return RedirectResponse(url="/equipas", status_code=303)
    try:
        rpe_exercicio = _normalizar_rpe(rpe)
        minutos_exercicio = _normalizar_minutos(minutos)
        bloco = _normalizar_bloco(bloco)
    except ValueError as erro:
        set_flash(request, str(erro), "error")
        return RedirectResponse(url=f"/treino/sessoes/{plano.sessao_id}", status_code=303)
    total_no_bloco = db.query(ExercicioPlano).filter(
        ExercicioPlano.plano_id == plano_id,
        ExercicioPlano.bloco == bloco,
    ).count()
    exercicio = ExercicioPlano(
        plano_id=plano_id,
        bloco=bloco,
        ordem=total_no_bloco + 1,
        hora=hora or None,
        minutos=minutos_exercicio,
        rpe=rpe_exercicio,
        nome=biblioteca.nome,
        categoria=biblioteca.categoria,
        desenho_1=biblioteca.desenho,
        desenho_2=biblioteca.desenho_campo_completo,
        organizacao=biblioteca.organizacao,
        coaching_points=biblioteca.coaching_points,
    )
    _marcar_sessao_como_alterada_manual(plano.sessao)
    db.add(exercicio)
    db.commit()
    set_flash(request, f"Exercício '{biblioteca.nome}' reutilizado no plano.")
    return RedirectResponse(url=f"/treino/sessoes/{plano.sessao_id}", status_code=303)


# ─────────────────────────────────────────
# APAGAR EXERCÍCIO
# URL: POST /treino/exercicios/{exercicio_id}/apagar
# ─────────────────────────────────────────
@router.post("/exercicios/{exercicio_id}/apagar")
async def apagar_exercicio(exercicio_id: int, request: Request, db: Session = Depends(get_db),
                           utilizador=Depends(exigir_autenticacao)):
    _verificar_acesso_treino(utilizador, _obter_equipa_id_por_exercicio(db, exercicio_id), db)

    exercicio = db.query(ExercicioPlano).filter(ExercicioPlano.id == exercicio_id).first()

    if exercicio:
        sessao_id = exercicio.plano.sessao_id
        plano_id = exercicio.plano_id
        bloco = exercicio.bloco or "A"
        _marcar_sessao_como_alterada_manual(exercicio.plano.sessao)
        db.delete(exercicio)
        db.commit()
        _reordenar_exercicios_bloco(db, plano_id, bloco)
        db.commit()
        return RedirectResponse(url=f"/treino/sessoes/{sessao_id}", status_code=303)

    return RedirectResponse(url="/equipas")


@router.post("/exercicios/{exercicio_id}/duplicar")
async def duplicar_exercicio(exercicio_id: int, request: Request, db: Session = Depends(get_db),
                             utilizador=Depends(exigir_autenticacao)):
    """Duplica um exercício no mesmo bloco para acelerar a construção da sessão."""
    _verificar_acesso_treino(utilizador, _obter_equipa_id_por_exercicio(db, exercicio_id), db)
    exercicio = db.query(ExercicioPlano).filter(ExercicioPlano.id == exercicio_id).first()
    if not exercicio:
        return RedirectResponse(url="/equipas", status_code=303)

    bloco = exercicio.bloco or "A"
    total_no_bloco = db.query(ExercicioPlano).filter(
        ExercicioPlano.plano_id == exercicio.plano_id,
        ExercicioPlano.bloco == bloco,
    ).count()
    copia = ExercicioPlano(
        plano_id=exercicio.plano_id,
        bloco=bloco,
        ordem=total_no_bloco + 1,
        hora=exercicio.hora,
        minutos=exercicio.minutos,
        rpe=exercicio.rpe,
        nome=exercicio.nome,
        categoria=exercicio.categoria,
        desenho_1=exercicio.desenho_1,
        desenho_2=exercicio.desenho_2,
        desenho_3=exercicio.desenho_3,
        desenho_4=exercicio.desenho_4,
        campos_ativos=exercicio.campos_ativos,
        organizacao=exercicio.organizacao,
        coaching_points=exercicio.coaching_points,
    )
    _marcar_sessao_como_alterada_manual(exercicio.plano.sessao)
    db.add(copia)
    db.commit()
    set_flash(request, "Exercício duplicado no mesmo bloco.")
    return RedirectResponse(url=f"/treino/sessoes/{exercicio.plano.sessao_id}#bloco-{bloco}", status_code=303)


@router.post("/exercicios/{exercicio_id}/atualizar")
async def atualizar_exercicio(
    exercicio_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
    bloco: str = Form("A"),
    bloco_id: str = Form(""),
    nome: str = Form(""),
    categoria: str = Form(""),
    hora: str = Form(""),
    minutos: str = Form(""),
    rpe: str = Form(""),
    organizacao: str = Form(""),
    coaching_points: str = Form(""),
):
    _verificar_acesso_treino(utilizador, _obter_equipa_id_por_exercicio(db, exercicio_id), db)

    exercicio = db.query(ExercicioPlano).filter(ExercicioPlano.id == exercicio_id).first()
    if not exercicio:
        return RedirectResponse(url="/equipas", status_code=303)

    bloco_anterior = exercicio.bloco or "A"
    bloco_novo = bloco or bloco_anterior
    bloco_dinamico_id = int(bloco_id) if bloco_id else exercicio.bloco_id

    try:
        exercicio.rpe = _normalizar_rpe(rpe)
        exercicio.minutos = _normalizar_minutos(minutos)
        bloco_novo = _normalizar_bloco(bloco) if not bloco_dinamico_id else bloco_anterior
    except ValueError as erro:
        set_flash(request, str(erro), "error")
        return RedirectResponse(url=f"/treino/sessoes/{exercicio.plano.sessao_id}", status_code=303)

    exercicio.nome = nome or None
    exercicio.categoria = categoria or None
    exercicio.hora = hora or None
    exercicio.organizacao = organizacao or None
    exercicio.coaching_points = coaching_points or None

    if bloco_dinamico_id != exercicio.bloco_id:
        exercicio.bloco_id = bloco_dinamico_id
        exercicio.bloco = None
        exercicio.ordem = db.query(ExercicioPlano).filter(ExercicioPlano.plano_id == exercicio.plano_id, ExercicioPlano.bloco_id == bloco_dinamico_id, ExercicioPlano.id != exercicio.id).count() + 1
    elif bloco_novo != bloco_anterior:
        exercicio.bloco = bloco_novo
        exercicio.ordem = (
            db.query(ExercicioPlano)
            .filter(
                ExercicioPlano.plano_id == exercicio.plano_id,
                ExercicioPlano.bloco == bloco_novo,
                ExercicioPlano.id != exercicio.id,
            )
            .count()
            + 1
        )

    _marcar_sessao_como_alterada_manual(exercicio.plano.sessao)
    db.commit()

    if bloco_novo != bloco_anterior:
        _reordenar_exercicios_bloco(db, exercicio.plano_id, bloco_anterior)
        _reordenar_exercicios_bloco(db, exercicio.plano_id, bloco_novo)
        db.commit()

    return RedirectResponse(url=f"/treino/sessoes/{exercicio.plano.sessao_id}", status_code=303)


# ─────────────────────────────────────────
# GUARDAR REFLEXÃO DO PLANO
# URL: POST /treino/planos/{plano_id}/reflexao
# ─────────────────────────────────────────
@router.post("/planos/{plano_id}/reflexao")
async def guardar_reflexao(
    plano_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
    reflexao: str = Form("")
):
    _verificar_acesso_treino(utilizador, _obter_equipa_id_por_plano(db, plano_id), db)

    plano = db.query(PlanoTreino).filter(PlanoTreino.id == plano_id).first()
    if plano:
        _marcar_sessao_como_alterada_manual(plano.sessao)
        plano.reflexao = reflexao or None
        if reflexao.strip() and normalizar_estado_sessao(plano.sessao.estado) == "executada":
            plano.sessao.estado = "registada"
        db.commit()

    return RedirectResponse(url=f"/treino/sessoes/{plano.sessao_id}", status_code=303)


# ─────────────────────────────────────────
# GUARDAR DESENHO DE UM EXERCÍCIO
# URL: POST /treino/exercicios/{exercicio_id}/desenho
# ─────────────────────────────────────────
@router.post("/exercicios/{exercicio_id}/desenho")
async def guardar_desenho(exercicio_id: int, request: Request, db: Session = Depends(get_db),
                          utilizador=Depends(exigir_autenticacao)):
    _verificar_acesso_treino(utilizador, _obter_equipa_id_por_exercicio(db, exercicio_id), db)

    dados = await request.json()
    numero = dados.get("numero")
    desenho_base64 = dados.get("dados")

    exercicio = db.query(ExercicioPlano).filter(ExercicioPlano.id == exercicio_id).first()

    if not exercicio:
        return JSONResponse({"sucesso": False, "erro": "Exercício não encontrado"})

    if numero not in TIPOS_CAMPO:
        return JSONResponse({"sucesso": False, "erro": "Campo inválido"}, status_code=422)

    setattr(exercicio, f"desenho_{numero}", desenho_base64)
    slots = _slots_ativos(exercicio)
    if numero not in slots:
        slots.append(numero)
        _definir_slots_ativos(exercicio, slots)

    _marcar_sessao_como_alterada_manual(exercicio.plano.sessao)
    db.commit()
    return JSONResponse({"sucesso": True})


@router.post("/exercicios/{exercicio_id}/campos")
async def adicionar_campo_exercicio(
    exercicio_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
    tipo: str = Form(...),
):
    _verificar_acesso_treino(utilizador, _obter_equipa_id_por_exercicio(db, exercicio_id), db)
    exercicio = db.query(ExercicioPlano).filter(ExercicioPlano.id == exercicio_id).first()
    if not exercicio:
        return RedirectResponse(url="/equipas", status_code=303)
    candidatos = [1, 3] if tipo == "meio" else [2, 4] if tipo == "completo" else []
    slots = _slots_ativos(exercicio)
    disponivel = next((numero for numero in candidatos if numero not in slots), None)
    if disponivel is None:
        set_flash(request, "Já atingiste o limite de dois campos deste tipo.", "error")
    else:
        slots.append(disponivel)
        _definir_slots_ativos(exercicio, slots)
        _marcar_sessao_como_alterada_manual(exercicio.plano.sessao)
        db.commit()
        set_flash(request, "Campo acrescentado ao exercício.")
    return RedirectResponse(url=f"/treino/sessoes/{exercicio.plano.sessao_id}#exercicio-{exercicio.id}", status_code=303)


@router.post("/exercicios/{exercicio_id}/campos/{numero}/apagar")
async def apagar_campo_exercicio(
    exercicio_id: int,
    numero: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    _verificar_acesso_treino(utilizador, _obter_equipa_id_por_exercicio(db, exercicio_id), db)
    exercicio = db.query(ExercicioPlano).filter(ExercicioPlano.id == exercicio_id).first()
    if not exercicio or numero not in TIPOS_CAMPO:
        return RedirectResponse(url="/equipas", status_code=303)
    _definir_slots_ativos(exercicio, [slot for slot in _slots_ativos(exercicio) if slot != numero])
    setattr(exercicio, f"desenho_{numero}", None)
    _marcar_sessao_como_alterada_manual(exercicio.plano.sessao)
    db.commit()
    set_flash(request, "Campo removido sem afetar os restantes.")
    return RedirectResponse(url=f"/treino/sessoes/{exercicio.plano.sessao_id}#exercicio-{exercicio.id}", status_code=303)


# ─────────────────────────────────────────
# VERSÃO DE IMPRESSÃO DO PLANO DE TREINO
# URL: GET /treino/sessoes/{sessao_id}/print
# ─────────────────────────────────────────
@router.get("/sessoes/{sessao_id}/print", response_class=HTMLResponse)
def imprimir_plano_treino(sessao_id: int, request: Request, db: Session = Depends(get_db),
                          utilizador=Depends(exigir_autenticacao)):
    _verificar_acesso_treino(utilizador, _obter_equipa_id_por_sessao(db, sessao_id), db)

    sessao = db.query(SessaoTreino).filter(SessaoTreino.id == sessao_id).first()
    if not sessao:
        return RedirectResponse(url="/equipas")
    sessao = enriquecer_sessao_para_ui(sessao)

    equipa = sessao.microciclo.mesociclo.macrociclo.equipa
    plano = db.query(PlanoTreino).filter(PlanoTreino.sessao_id == sessao_id).first()

    return templates.TemplateResponse(
        request,
        "treino/plano_print.html",
        _contexto_impressao_plano(request, sessao, equipa, plano, utilizador),
    )


# ─────────────────────────────────────────
# EXPORTAR PDF DO PLANO DE TREINO
# URL: GET /treino/sessoes/{sessao_id}/pdf
# ─────────────────────────────────────────
@router.get("/sessoes/{sessao_id}/pdf")
def exportar_pdf_plano(sessao_id: int, request: Request, db: Session = Depends(get_db),
                       utilizador=Depends(exigir_autenticacao)):
    _verificar_acesso_treino(utilizador, _obter_equipa_id_por_sessao(db, sessao_id), db)

    sessao = db.query(SessaoTreino).filter(SessaoTreino.id == sessao_id).first()
    if not sessao:
        return RedirectResponse(url="/equipas")
    sessao = enriquecer_sessao_para_ui(sessao)

    equipa = sessao.microciclo.mesociclo.macrociclo.equipa
    plano = db.query(PlanoTreino).filter(PlanoTreino.sessao_id == sessao_id).first()

    contexto_pdf = _contexto_impressao_plano(request, sessao, equipa, plano, utilizador)
    contexto_pdf["modo_pdf"] = True
    pdf = renderizar_pdf(request, "treino/plano_print.html", contexto_pdf)

    nome = f"plano_treino_{equipa.nome}_{sessao.data}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={nome}"}
    )

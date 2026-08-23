# ─────────────────────────────────────────────────────────────
# ROUTER DE PLANEAMENTO
# Este ficheiro gere todas as rotas relacionadas com o
# planeamento desportivo: macrociclos, mesociclos e microciclos
# ─────────────────────────────────────────────────────────────

# APIRouter permite criar um conjunto de rotas separado do main.py
# Isto chama-se "separação de responsabilidades" — cada ficheiro
# trata de um tema específico
import json
from datetime import date, timedelta
from io import BytesIO
from urllib.parse import urlencode

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
from template_config import Jinja2Templates
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from sqlalchemy.orm import Session

from auth import verificar_acesso_equipa
from auth_deps import AcessoNegado, exigir_autenticacao
from flash import set_flash
from horarios import hora_eh_anterior, hora_valida, normalizar_hora

# Importamos a função get_db que abre e fecha sessões com a BD
from database import get_db
from paths import TEMPLATES_DIR
from services.planeamento_integrado_service import obter_dashboard_planeamento_equipa
from services.pdf_service import renderizar_pdf
from services.sincronizacao_ui import preparar_sessoes_para_ui, sessao_corresponde_filtro

# Importamos os modelos que vamos precisar
from models.planeamento import (
    ConteudoSessaoTreino,
    Macrociclo,
    Mesociclo,
    Microciclo,
    PlaneamentoAnualEquipa,
    SessaoTreino,
)
from models.planeamento_clube import EventoPlaneamentoClube, PlaneamentoClubeAnual, TipoEventoPlaneamentoClubeEnum
from models.atribuicao_espaco_semanal import (
    AtribuicaoEspacoSemanal,
    EstadoAtribuicaoEspacoEnum,
)
from models.equipa import Equipa
from models.espaco_treino import EspacoTreino
from models.jogo import Jogo
from services.agenda_service import tipos_agenda_formulario
from services.planeamento_objetivos_service import contexto_objetivos_superiores, objetivos_por_categoria
from services.numeracao_planeamento_service import (
    renumerar_macrociclos,
    renumerar_mesociclos,
    renumerar_microciclos,
)
from services.conteudos_sessao_service import (
    CATEGORIAS_POR_CODIGO,
    atualizar_minutos_por_componente,
    categorias_conteudo_para_ui,
    construir_visao_semanal_conteudos,
)

# prefix="/planeamento" significa que todas as rotas deste router
# começam com /planeamento — ex: /planeamento/macrociclos
router = APIRouter(prefix="/planeamento")

# Jinja2Templates aponta para a pasta onde estão os ficheiros HTML
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _verificar_acesso_planeamento(utilizador, equipa_id: int | None, db: Session) -> None:
    """Valida se o utilizador pode aceder ao planeamento; lança AcessoNegado se não."""
    if not equipa_id or not verificar_acesso_equipa(utilizador, equipa_id, db):
        raise AcessoNegado("/equipas")


def _obter_equipa_id_por_macrociclo(db: Session, macro_id: int) -> int | None:
    """Resolve a equipa associada a um macrociclo."""
    macrociclo = db.query(Macrociclo).filter(Macrociclo.id == macro_id).first()
    return macrociclo.equipa_id if macrociclo else None


def _obter_equipa_id_por_anual(db: Session, anual_id: int) -> int | None:
    anual = db.query(PlaneamentoAnualEquipa).filter(PlaneamentoAnualEquipa.id == anual_id).first()
    return anual.equipa_id if anual else None


def _epoca_para_data(data_inicio: date) -> str:
    ano = data_inicio.year if data_inicio.month >= 7 else data_inicio.year - 1
    return f"{ano}/{ano + 1}"


def _obter_ou_criar_anual_equipa(
    db: Session,
    equipa: Equipa,
    data_inicio: date,
    data_fim: date,
) -> PlaneamentoAnualEquipa:
    anual = db.query(PlaneamentoAnualEquipa).filter(
        PlaneamentoAnualEquipa.equipa_id == equipa.id,
        PlaneamentoAnualEquipa.data_inicio <= data_inicio,
        PlaneamentoAnualEquipa.data_fim >= data_fim,
    ).first()
    if anual:
        return anual

    anual_clube = db.query(PlaneamentoClubeAnual).filter(
        PlaneamentoClubeAnual.data_inicio <= data_inicio,
        PlaneamentoClubeAnual.data_fim >= data_fim,
    ).first()
    epoca = _epoca_para_data(data_inicio)
    anual = PlaneamentoAnualEquipa(
        equipa_id=equipa.id,
        planeamento_clube_anual_id=anual_clube.id if anual_clube else None,
        epoca=epoca,
        titulo=f"Planeamento anual {epoca}",
        data_inicio=data_inicio,
        data_fim=data_fim,
        objetivos_gerais=anual_clube.objetivos_gerais if anual_clube else None,
    )
    db.add(anual)
    db.flush()
    return anual


def _obter_equipa_id_por_mesociclo(db: Session, meso_id: int) -> int | None:
    """Resolve a equipa associada a um mesociclo."""
    mesociclo = db.query(Mesociclo).filter(Mesociclo.id == meso_id).first()
    return mesociclo.macrociclo.equipa_id if mesociclo and mesociclo.macrociclo else None


def _obter_equipa_id_por_microciclo(db: Session, micro_id: int) -> int | None:
    """Resolve a equipa associada a um microciclo."""
    microciclo = db.query(Microciclo).filter(Microciclo.id == micro_id).first()
    if not microciclo or not microciclo.mesociclo or not microciclo.mesociclo.macrociclo:
        return None
    return microciclo.mesociclo.macrociclo.equipa_id


def _normalizar_texto_comparacao(valor: str | None) -> str:
    """Normaliza texto livre para comparações simples."""
    return (valor or "").strip().lower()


def _contexto_agenda(
    *,
    equipa_id: int,
    data_inicio: date,
    data_fim: date,
    macrociclo_id: int | None = None,
    mesociclo_id: int | None = None,
    microciclo_id: int | None = None,
    retorno: str | None = None,
) -> dict:
    return {
        "equipa_id": equipa_id,
        "macrociclo_id": macrociclo_id or "",
        "mesociclo_id": mesociclo_id or "",
        "microciclo_id": microciclo_id or "",
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        "retorno": retorno or (
            f"/planeamento/microciclos/{microciclo_id}" if microciclo_id
            else f"/planeamento/mesociclos/{mesociclo_id}" if mesociclo_id
            else f"/planeamento/macrociclos/{macrociclo_id}"
        ),
    }


def _duracao_evento_minutos(hora_inicio: str | None, hora_fim: str | None) -> int | None:
    if not hora_inicio or not hora_fim:
        return None
    try:
        inicio = int(hora_inicio[:2]) * 60 + int(hora_inicio[3:])
        fim = int(hora_fim[:2]) * 60 + int(hora_fim[3:])
    except (TypeError, ValueError):
        return None
    return max(0, fim - inicio)


def _integrar_eventos_planeados_no_microciclo(db: Session, microciclo: Microciclo) -> int:
    """Materializa na semana técnica eventos da equipa já marcados acima na época."""
    equipa_id = microciclo.mesociclo.macrociclo.equipa_id
    eventos = db.query(EventoPlaneamentoClube).filter(
        EventoPlaneamentoClube.equipa_id == equipa_id,
        EventoPlaneamentoClube.data >= microciclo.data_inicio,
        EventoPlaneamentoClube.data <= microciclo.data_fim,
        EventoPlaneamentoClube.ativo.is_(True),
        EventoPlaneamentoClube.tipo.in_([
            TipoEventoPlaneamentoClubeEnum.treino_equipa,
            TipoEventoPlaneamentoClubeEnum.treino_individual,
            TipoEventoPlaneamentoClubeEnum.jogo,
        ]),
    ).order_by(EventoPlaneamentoClube.data, EventoPlaneamentoClube.hora_inicio, EventoPlaneamentoClube.id).all()
    criadas = 0
    for evento in eventos:
        existe = db.query(SessaoTreino).filter(
            SessaoTreino.microciclo_id == microciclo.id,
            SessaoTreino.evento_planeamento_clube_id == evento.id,
        ).first()
        evento.macrociclo_id = microciclo.mesociclo.macrociclo_id
        evento.mesociclo_id = microciclo.mesociclo_id
        evento.microciclo_id = microciclo.id
        if existe:
            continue
        e_jogo = evento.tipo == TipoEventoPlaneamentoClubeEnum.jogo
        numero = None if e_jogo else (
            db.query(SessaoTreino).filter(
                SessaoTreino.microciclo_id == microciclo.id,
                SessaoTreino.e_jogo.is_(False),
            ).count() + 1
        )
        db.add(SessaoTreino(
            clube_id=evento.clube_id,
            data=evento.data,
            local=evento.espaco.nome if evento.espaco else None,
            hora_inicio=evento.hora_inicio,
            hora_fim=evento.hora_fim,
            volume_minutos=_duracao_evento_minutos(evento.hora_inicio, evento.hora_fim) if not e_jogo else None,
            intensidade_rpe=0 if not e_jogo and evento.espaco_id else None,
            numero_treino=numero,
            e_jogo=e_jogo,
            origem="planeamento_integrado",
            sincronizada=True,
            alterada_manual=False,
            ativa=True,
            estado="planeada",
            microciclo_id=microciclo.id,
            plano_semanal_clube_id=evento.plano_semanal_id,
            evento_planeamento_clube_id=evento.id,
        ))
        criadas += 1
    return criadas


def _validar_intervalo_horario_sessao(hora_inicio: str | None, hora_fim: str | None) -> str | None:
    """Garante coerência mínima no horário da sessão."""
    if not hora_valida(hora_inicio) or not hora_valida(hora_fim):
        return "As horas da sessão devem estar no formato HH:MM."
    hora_inicio_normalizada = normalizar_hora(hora_inicio)
    hora_fim_normalizada = normalizar_hora(hora_fim)
    if hora_inicio_normalizada and hora_fim_normalizada and not hora_eh_anterior(
        hora_inicio_normalizada,
        hora_fim_normalizada,
    ):
        return "A hora de início tem de ser anterior à hora de término."
    return None


def _ordenar_sessoes_microciclo(sessoes: list[SessaoTreino]) -> list[SessaoTreino]:
    """Ordena sessões por data, hora de início e identificador."""
    return sorted(
        sessoes,
        key=lambda sessao: (
            sessao.data or date.min,
            sessao.hora_inicio or "99:99",
            sessao.id or 0,
        ),
    )


def _obter_nome_dia_semana(data_sessao: date | None) -> str:
    """Devolve o nome do dia da semana em português."""
    if not data_sessao:
        return ""
    dias_semana = [
        "Segunda-feira",
        "Terça-feira",
        "Quarta-feira",
        "Quinta-feira",
        "Sexta-feira",
        "Sábado",
        "Domingo",
    ]
    return dias_semana[data_sessao.weekday()]


def _formatar_intervalo_sessao(sessao: SessaoTreino) -> str:
    """Compõe um texto curto com o horário da sessão."""
    if sessao.hora_inicio and sessao.hora_fim:
        return f"{sessao.hora_inicio} - {sessao.hora_fim}"
    if sessao.hora_inicio:
        return sessao.hora_inicio
    if sessao.hora_fim:
        return f"Até {sessao.hora_fim}"
    return "Por definir"


def _obter_tipo_legivel_sessao(sessao: SessaoTreino) -> str:
    """Traduz a sessão para uma label curta legível."""
    if sessao.e_jogo:
        return "Jogo"
    if sessao.numero_treino is not None:
        return f"Treino {sessao.numero_treino}"
    return "Treino"


def _construir_calendario_microciclo(sessoes: list[SessaoTreino]) -> list[dict]:
    """Converte as sessões do microciclo num quadro semanal simples."""
    calendario = []
    for sessao in _ordenar_sessoes_microciclo(sessoes):
        calendario.append({
            "sessao": sessao,
            "dia_semana": _obter_nome_dia_semana(sessao.data),
            "intervalo_horario": _formatar_intervalo_sessao(sessao),
            "tipo_label": _obter_tipo_legivel_sessao(sessao),
            "link": f"/treino/sessoes/{sessao.id}",
        })
    return calendario


def _agrupar_exercicios_por_bloco(plano) -> dict[str, list]:
    """Agrupa os exercícios do plano pelos blocos esperados no template."""
    exercicios_por_bloco = {"A": [], "B": [], "C": [], "D": []}
    if not plano:
        return exercicios_por_bloco
    for exercicio in plano.exercicios:
        bloco = exercicio.bloco or "A"
        exercicios_por_bloco.setdefault(bloco, []).append(exercicio)
    return exercicios_por_bloco


def _calcular_balanco_microciclo(sessoes_ativas: list[SessaoTreino]) -> tuple[dict, dict]:
    """Calcula o balanço estatístico e os dados dos gráficos do microciclo."""
    sessoes_ordenadas = _ordenar_sessoes_microciclo(sessoes_ativas)
    treinos = [s for s in sessoes_ordenadas if not s.e_jogo]
    jogos = [s for s in sessoes_ordenadas if s.e_jogo]

    volume_total = sum(s.volume_minutos or 0 for s in treinos)
    rpes_validos = [s.intensidade_rpe for s in treinos if s.intensidade_rpe]
    media_rpe = round(sum(rpes_validos) / len(rpes_validos), 1) if rpes_validos else 0

    componentes = {
        "TIO": sum(s.min_tecnica_individual_ofensiva or 0 for s in treinos),
        "TID": sum(s.min_tecnica_individual_defensiva or 0 for s in treinos),
        "TaIO": sum(s.min_tatica_individual_ofensiva or 0 for s in treinos),
        "TaID": sum(s.min_tatica_individual_defensiva or 0 for s in treinos),
        "TCO": sum(s.min_tatica_coletiva_ofensiva or 0 for s in treinos),
        "TCD": sum(s.min_tatica_coletiva_defensiva or 0 for s in treinos),
        "FÍS": sum(s.min_fisicos or 0 for s in treinos),
        "PSI": sum(s.min_psicologicos or 0 for s in treinos),
    }

    balanco = {
        "treinos_previstos": len(treinos),
        "treinos_realizados": len(treinos),
        "jogos_previstos": len(jogos),
        "jogos_realizados": len(jogos),
        "volume_total": volume_total,
        "media_rpe": media_rpe,
        "componentes": componentes,
    }

    dados_graficos = {
        "labels": [s.data.isoformat() if s.data else "" for s in sessoes_ordenadas],
        "volumes": [s.volume_minutos if s.volume_minutos else 0 for s in sessoes_ordenadas],
        "rpes": [float(s.intensidade_rpe) if s.intensidade_rpe else 0 for s in sessoes_ordenadas],
    }

    return balanco, dados_graficos


def _calcular_resumo_assiduidade_microciclo(db: Session, equipa_id: int, sessoes: list[SessaoTreino]) -> dict:
    """Resume as presenças ligadas ao microciclo sem duplicar a grelha diária."""
    from models.assiduidade import RegistoAssiduidade

    sessao_ids = [sessao.id for sessao in sessoes if sessao.id]
    if not sessao_ids:
        return {"registos": 0, "presentes": 0, "percentagem": 0}

    registos = db.query(RegistoAssiduidade).filter(
        RegistoAssiduidade.sessao_id.in_(sessao_ids),
    ).all()
    presentes = sum(1 for registo in registos if registo.presente)
    percentagem = round(presentes * 100 / len(registos), 1) if registos else 0
    return {
        "registos": len(registos),
        "presentes": presentes,
        "percentagem": percentagem,
    }


def _verificar_divergencia_atribuicao(db, sessao_data, equipa_id, local_planeado):
    """
    Verifica se existe atribuição de espaço global para esta equipa nesta data.

    Returns:
    {
      "tem_atribuicao": bool,
      "atribuicao": AtribuicaoEspacoSemanal | None,
      "divergente": bool,
      "mensagem": str | None
    }
    """
    atribuicao = db.query(AtribuicaoEspacoSemanal).filter(
        AtribuicaoEspacoSemanal.equipa_id == equipa_id,
        AtribuicaoEspacoSemanal.data == sessao_data,
        AtribuicaoEspacoSemanal.estado != EstadoAtribuicaoEspacoEnum.cancelado,
    ).order_by(
        AtribuicaoEspacoSemanal.hora_inicio.asc(),
        AtribuicaoEspacoSemanal.id.asc(),
    ).first()

    if not atribuicao:
        return {
            "tem_atribuicao": False,
            "atribuicao": None,
            "divergente": False,
            "mensagem": None,
        }

    nome_espaco_atribuido = atribuicao.espaco.nome if atribuicao.espaco else None
    local_planeado_normalizado = _normalizar_texto_comparacao(local_planeado)
    local_atribuido_normalizado = _normalizar_texto_comparacao(nome_espaco_atribuido)

    local_divergente = bool(
        local_planeado_normalizado
        and local_atribuido_normalizado
        and local_planeado_normalizado != local_atribuido_normalizado
    )

    mensagem = None
    if local_divergente:
        mensagem = (
            "Atenção: esta sessão está planeada fora do espaço atribuído pelo clube."
        )

    return {
        "tem_atribuicao": True,
        "atribuicao": atribuicao,
        "divergente": local_divergente,
        "mensagem": mensagem,
    }


# ─────────────────────────────────────────
# PLANEAMENTO ANUAL DA EQUIPA
# ─────────────────────────────────────────
@router.get("/equipas/{equipa_id}/anuais", response_class=HTMLResponse)
def listar_planeamentos_anuais_equipa(
    equipa_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    _verificar_acesso_planeamento(utilizador, equipa_id, db)
    equipa = db.query(Equipa).filter(Equipa.id == equipa_id).first()
    if not equipa:
        return RedirectResponse(url="/equipas", status_code=303)
    planeamentos = db.query(PlaneamentoAnualEquipa).filter(
        PlaneamentoAnualEquipa.equipa_id == equipa_id,
    ).order_by(PlaneamentoAnualEquipa.data_inicio.desc()).all()
    return templates.TemplateResponse(request, "planeamento/anuais/lista.html", {
        "utilizador": utilizador,
        "equipa": equipa,
        "planeamentos": planeamentos,
    })


def _contexto_form_anual_equipa(db: Session, equipa: Equipa) -> dict:
    return {
        "equipa": equipa,
        "planeamentos_clube": db.query(PlaneamentoClubeAnual).order_by(
            PlaneamentoClubeAnual.data_inicio.desc(),
        ).all(),
    }


@router.get("/equipas/{equipa_id}/anuais/novo", response_class=HTMLResponse)
def form_novo_anual_equipa(
    equipa_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    _verificar_acesso_planeamento(utilizador, equipa_id, db)
    equipa = db.query(Equipa).filter(Equipa.id == equipa_id).first()
    if not equipa:
        return RedirectResponse(url="/equipas", status_code=303)
    contexto = _contexto_form_anual_equipa(db, equipa)
    contexto.update({"utilizador": utilizador, "planeamento": None})
    return templates.TemplateResponse(request, "planeamento/anuais/form.html", contexto)


def _aplicar_dados_anual_equipa(
    planeamento: PlaneamentoAnualEquipa,
    *,
    epoca: str,
    titulo: str,
    data_inicio: str,
    data_fim: str,
    planeamento_clube_anual_id: str,
    objetivos_gerais: str,
    obj_tecnica_individual_ofensiva: str,
    obj_tecnica_individual_defensiva: str,
    obj_tatica_individual_ofensiva: str,
    obj_tatica_individual_defensiva: str,
    obj_tatica_coletiva_ofensiva: str,
    obj_tatica_coletiva_defensiva: str,
    obj_fisicos: str,
    obj_psicologicos: str,
    reflexao: str,
    estado: str,
) -> None:
    inicio = date.fromisoformat(data_inicio)
    fim = date.fromisoformat(data_fim)
    if inicio > fim:
        raise ValueError("A data de início não pode ser posterior à data de fim.")
    planeamento.epoca = epoca.strip()
    planeamento.titulo = titulo.strip()
    planeamento.data_inicio = inicio
    planeamento.data_fim = fim
    planeamento.planeamento_clube_anual_id = int(planeamento_clube_anual_id) if planeamento_clube_anual_id else None
    planeamento.objetivos_gerais = objetivos_gerais.strip() or None
    planeamento.obj_tecnica_individual_ofensiva = obj_tecnica_individual_ofensiva.strip() or None
    planeamento.obj_tecnica_individual_defensiva = obj_tecnica_individual_defensiva.strip() or None
    planeamento.obj_tatica_individual_ofensiva = obj_tatica_individual_ofensiva.strip() or None
    planeamento.obj_tatica_individual_defensiva = obj_tatica_individual_defensiva.strip() or None
    planeamento.obj_tatica_coletiva_ofensiva = obj_tatica_coletiva_ofensiva.strip() or None
    planeamento.obj_tatica_coletiva_defensiva = obj_tatica_coletiva_defensiva.strip() or None
    planeamento.obj_fisicos = obj_fisicos.strip() or None
    planeamento.obj_psicologicos = obj_psicologicos.strip() or None
    planeamento.reflexao = reflexao.strip() or None
    planeamento.estado = estado if estado in {"rascunho", "ativo", "concluido"} else "rascunho"


@router.post("/equipas/{equipa_id}/anuais/novo")
async def criar_anual_equipa(
    equipa_id: int, request: Request, db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao), epoca: str = Form(...), titulo: str = Form(...),
    data_inicio: str = Form(...), data_fim: str = Form(...), planeamento_clube_anual_id: str = Form(""),
    objetivos_gerais: str = Form(""), obj_tecnica_individual_ofensiva: str = Form(""),
    obj_tecnica_individual_defensiva: str = Form(""), obj_tatica_individual_ofensiva: str = Form(""),
    obj_tatica_individual_defensiva: str = Form(""), obj_tatica_coletiva_ofensiva: str = Form(""),
    obj_tatica_coletiva_defensiva: str = Form(""), obj_fisicos: str = Form(""),
    obj_psicologicos: str = Form(""), reflexao: str = Form(""), estado: str = Form("rascunho"),
):
    _verificar_acesso_planeamento(utilizador, equipa_id, db)
    equipa = db.query(Equipa).filter(Equipa.id == equipa_id).first()
    if not equipa:
        return RedirectResponse(url="/equipas", status_code=303)
    planeamento = PlaneamentoAnualEquipa(equipa_id=equipa_id)
    _aplicar_dados_anual_equipa(planeamento, **{
        "epoca": epoca, "titulo": titulo, "data_inicio": data_inicio, "data_fim": data_fim,
        "planeamento_clube_anual_id": planeamento_clube_anual_id, "objetivos_gerais": objetivos_gerais,
        "obj_tecnica_individual_ofensiva": obj_tecnica_individual_ofensiva,
        "obj_tecnica_individual_defensiva": obj_tecnica_individual_defensiva,
        "obj_tatica_individual_ofensiva": obj_tatica_individual_ofensiva,
        "obj_tatica_individual_defensiva": obj_tatica_individual_defensiva,
        "obj_tatica_coletiva_ofensiva": obj_tatica_coletiva_ofensiva,
        "obj_tatica_coletiva_defensiva": obj_tatica_coletiva_defensiva,
        "obj_fisicos": obj_fisicos, "obj_psicologicos": obj_psicologicos,
        "reflexao": reflexao, "estado": estado,
    })
    if planeamento.planeamento_clube_anual_id:
        anual_clube = db.query(PlaneamentoClubeAnual).filter(
            PlaneamentoClubeAnual.id == planeamento.planeamento_clube_anual_id,
        ).first()
        if not anual_clube:
            raise AcessoNegado(f"/planeamento/equipas/{equipa_id}/anuais")
        if not planeamento.objetivos_gerais:
            planeamento.objetivos_gerais = anual_clube.objetivos_gerais
    db.add(planeamento)
    db.commit()
    set_flash(request, "Planeamento anual da equipa criado.")
    return RedirectResponse(url=f"/planeamento/anuais/{planeamento.id}", status_code=303)


@router.get("/anuais/{anual_id}", response_class=HTMLResponse)
def detalhe_anual_equipa(
    anual_id: int, request: Request, db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    _verificar_acesso_planeamento(utilizador, _obter_equipa_id_por_anual(db, anual_id), db)
    planeamento = db.query(PlaneamentoAnualEquipa).filter(PlaneamentoAnualEquipa.id == anual_id).first()
    if not planeamento:
        return RedirectResponse(url="/equipas", status_code=303)
    macrociclos = db.query(Macrociclo).filter(
        Macrociclo.planeamento_anual_equipa_id == anual_id,
    ).order_by(Macrociclo.numero).all()
    dashboard_planeamento = obter_dashboard_planeamento_equipa(
        db,
        planeamento.equipa_id,
        planeamento.data_inicio,
        planeamento.data_fim,
    )
    return templates.TemplateResponse(request, "planeamento/anuais/detalhe.html", {
        "utilizador": utilizador,
        "planeamento": planeamento,
        "equipa": planeamento.equipa,
        "macrociclos": macrociclos,
        "dashboard_planeamento": dashboard_planeamento,
        "objetivos_por_categoria": objetivos_por_categoria(planeamento),
        "agenda_contexto": _contexto_agenda(
            equipa_id=planeamento.equipa_id,
            data_inicio=planeamento.data_inicio,
            data_fim=planeamento.data_fim,
            retorno=f"/planeamento/anuais/{planeamento.id}",
        ),
        "agenda_tipos": tipos_agenda_formulario(),
        "espacos_agenda": db.query(EspacoTreino).filter(EspacoTreino.ativo.is_(True)).order_by(EspacoTreino.nome).all(),
    })


@router.get("/anuais/{anual_id}/editar", response_class=HTMLResponse)
def form_editar_anual_equipa(
    anual_id: int, request: Request, db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    _verificar_acesso_planeamento(utilizador, _obter_equipa_id_por_anual(db, anual_id), db)
    planeamento = db.query(PlaneamentoAnualEquipa).filter(PlaneamentoAnualEquipa.id == anual_id).first()
    if not planeamento:
        return RedirectResponse(url="/equipas", status_code=303)
    contexto = _contexto_form_anual_equipa(db, planeamento.equipa)
    contexto.update({"utilizador": utilizador, "planeamento": planeamento})
    return templates.TemplateResponse(request, "planeamento/anuais/form.html", contexto)


@router.post("/anuais/{anual_id}/editar")
async def editar_anual_equipa(
    anual_id: int, request: Request, db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao), epoca: str = Form(...), titulo: str = Form(...),
    data_inicio: str = Form(...), data_fim: str = Form(...), planeamento_clube_anual_id: str = Form(""),
    objetivos_gerais: str = Form(""), obj_tecnica_individual_ofensiva: str = Form(""),
    obj_tecnica_individual_defensiva: str = Form(""), obj_tatica_individual_ofensiva: str = Form(""),
    obj_tatica_individual_defensiva: str = Form(""), obj_tatica_coletiva_ofensiva: str = Form(""),
    obj_tatica_coletiva_defensiva: str = Form(""), obj_fisicos: str = Form(""),
    obj_psicologicos: str = Form(""), reflexao: str = Form(""), estado: str = Form("rascunho"),
):
    _verificar_acesso_planeamento(utilizador, _obter_equipa_id_por_anual(db, anual_id), db)
    planeamento = db.query(PlaneamentoAnualEquipa).filter(PlaneamentoAnualEquipa.id == anual_id).first()
    if not planeamento:
        return RedirectResponse(url="/equipas", status_code=303)
    _aplicar_dados_anual_equipa(planeamento, **{
        "epoca": epoca, "titulo": titulo, "data_inicio": data_inicio, "data_fim": data_fim,
        "planeamento_clube_anual_id": planeamento_clube_anual_id, "objetivos_gerais": objetivos_gerais,
        "obj_tecnica_individual_ofensiva": obj_tecnica_individual_ofensiva,
        "obj_tecnica_individual_defensiva": obj_tecnica_individual_defensiva,
        "obj_tatica_individual_ofensiva": obj_tatica_individual_ofensiva,
        "obj_tatica_individual_defensiva": obj_tatica_individual_defensiva,
        "obj_tatica_coletiva_ofensiva": obj_tatica_coletiva_ofensiva,
        "obj_tatica_coletiva_defensiva": obj_tatica_coletiva_defensiva,
        "obj_fisicos": obj_fisicos, "obj_psicologicos": obj_psicologicos,
        "reflexao": reflexao, "estado": estado,
    })
    if planeamento.planeamento_clube_anual_id and not db.query(PlaneamentoClubeAnual).filter(
        PlaneamentoClubeAnual.id == planeamento.planeamento_clube_anual_id,
    ).first():
        raise AcessoNegado(f"/planeamento/anuais/{anual_id}/editar")
    macro_fora_periodo = db.query(Macrociclo).filter(
        Macrociclo.planeamento_anual_equipa_id == anual_id,
        (Macrociclo.data_inicio < planeamento.data_inicio) | (Macrociclo.data_fim > planeamento.data_fim),
    ).first()
    if macro_fora_periodo:
        db.rollback()
        set_flash(request, "As novas datas deixam macrociclos fora do planeamento anual.", "erro")
        return RedirectResponse(url=f"/planeamento/anuais/{anual_id}/editar", status_code=303)
    db.commit()
    set_flash(request, "Planeamento anual da equipa atualizado.")
    return RedirectResponse(url=f"/planeamento/anuais/{anual_id}", status_code=303)


@router.post("/anuais/{anual_id}/eliminar")
async def eliminar_anual_equipa(
    anual_id: int, request: Request, db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    equipa_id = _obter_equipa_id_por_anual(db, anual_id)
    _verificar_acesso_planeamento(utilizador, equipa_id, db)
    planeamento = db.query(PlaneamentoAnualEquipa).filter(PlaneamentoAnualEquipa.id == anual_id).first()
    if planeamento:
        db.delete(planeamento)
        db.commit()
        set_flash(request, "Planeamento anual da equipa eliminado.")
    return RedirectResponse(url=f"/planeamento/equipas/{equipa_id}/anuais", status_code=303)


# ─────────────────────────────────────────
# LISTA DE MACROCICLOS DE UMA EQUIPA
# URL: GET /planeamento/equipas/{equipa_id}/macrociclos
# ─────────────────────────────────────────
@router.get("/equipas/{equipa_id}/macrociclos", response_class=HTMLResponse)
def listar_macrociclos(equipa_id: int, request: Request, db: Session = Depends(get_db),
                       utilizador=Depends(exigir_autenticacao)):
    _verificar_acesso_planeamento(utilizador, equipa_id, db)
    equipa = db.query(Equipa).filter(Equipa.id == equipa_id).first()
    if not equipa:
        return RedirectResponse(url="/equipas", status_code=303)

    macrociclos = db.query(Macrociclo).filter(
        Macrociclo.equipa_id == equipa_id,
    ).order_by(Macrociclo.data_inicio.desc(), Macrociclo.numero.desc()).all()
    return templates.TemplateResponse(request, "planeamento/macrociclos/lista.html", {
        "utilizador": utilizador,
        "equipa": equipa,
        "macrociclos": macrociclos,
    })


@router.get("/equipas/{equipa_id}/mesociclos", response_class=HTMLResponse)
def listar_mesociclos_equipa(
    equipa_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    """Lista todos os mesociclos da equipa sem exigir a abertura de um macro."""
    _verificar_acesso_planeamento(utilizador, equipa_id, db)
    equipa = db.query(Equipa).filter(Equipa.id == equipa_id).first()
    if not equipa:
        return RedirectResponse(url="/equipas", status_code=303)

    macrociclos = db.query(Macrociclo).filter(
        Macrociclo.equipa_id == equipa_id,
    ).order_by(Macrociclo.data_inicio.desc(), Macrociclo.numero.desc()).all()
    mesociclos = db.query(Mesociclo).join(Macrociclo).filter(
        Macrociclo.equipa_id == equipa_id,
    ).order_by(Mesociclo.data_inicio.desc(), Mesociclo.numero.desc()).all()
    return templates.TemplateResponse(request, "planeamento/mesociclos/lista_equipa.html", {
        "utilizador": utilizador,
        "equipa": equipa,
        "macrociclos": macrociclos,
        "mesociclos": mesociclos,
    })


@router.get("/equipas/{equipa_id}/microciclos", response_class=HTMLResponse)
def listar_microciclos_equipa(
    equipa_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    """Lista todos os microciclos da equipa sem exigir a abertura de um meso."""
    _verificar_acesso_planeamento(utilizador, equipa_id, db)
    equipa = db.query(Equipa).filter(Equipa.id == equipa_id).first()
    if not equipa:
        return RedirectResponse(url="/equipas", status_code=303)

    mesociclos = db.query(Mesociclo).join(Macrociclo).filter(
        Macrociclo.equipa_id == equipa_id,
    ).order_by(Mesociclo.data_inicio.desc(), Mesociclo.numero.desc()).all()
    microciclos = db.query(Microciclo).join(Mesociclo).join(Macrociclo).filter(
        Macrociclo.equipa_id == equipa_id,
    ).order_by(Microciclo.data_inicio.desc(), Microciclo.numero.desc()).all()
    return templates.TemplateResponse(request, "planeamento/microciclos/lista_equipa.html", {
        "utilizador": utilizador,
        "equipa": equipa,
        "mesociclos": mesociclos,
        "microciclos": microciclos,
    })


# ─────────────────────────────────────────
# FORMULÁRIO DE CRIAR MACROCICLO
# URL: GET /planeamento/equipas/{equipa_id}/macrociclos/novo
# ─────────────────────────────────────────
@router.get("/equipas/{equipa_id}/macrociclos/novo", response_class=HTMLResponse)
def form_novo_macrociclo(equipa_id: int, request: Request, db: Session = Depends(get_db),
                         utilizador=Depends(exigir_autenticacao), anual_id: int | None = None):
    _verificar_acesso_planeamento(utilizador, equipa_id, db)

    equipa = db.query(Equipa).filter(Equipa.id == equipa_id).first()
    if not equipa:
        return RedirectResponse(url="/equipas")

    planeamento_anual = None
    if anual_id:
        planeamento_anual = db.query(PlaneamentoAnualEquipa).filter(
            PlaneamentoAnualEquipa.id == anual_id,
            PlaneamentoAnualEquipa.equipa_id == equipa_id,
        ).first()
    if not planeamento_anual:
        planeamento_anual = db.query(PlaneamentoAnualEquipa).filter(
            PlaneamentoAnualEquipa.equipa_id == equipa_id,
        ).order_by(PlaneamentoAnualEquipa.data_inicio.desc()).first()
    if not planeamento_anual:
        set_flash(request, "Cria primeiro o planeamento anual da equipa.", "info")
        return RedirectResponse(url=f"/planeamento/equipas/{equipa_id}/anuais/novo", status_code=303)

    total_macros = db.query(Macrociclo).filter(
        Macrociclo.planeamento_anual_equipa_id == planeamento_anual.id,
    ).count()

    # O número do novo macro é o total actual + 1
    # Ex: se já existem 2 macros, o novo é o número 3
    proximo_numero = total_macros + 1

    return templates.TemplateResponse(request, "planeamento/macrociclos/form.html", {
        "utilizador": utilizador,
        "equipa": equipa,
        "proximo_numero": proximo_numero,
        "planeamento_anual_equipa": planeamento_anual,
    })


# ─────────────────────────────────────────
# CRIAR MACROCICLO
# URL: POST /planeamento/equipas/{equipa_id}/macrociclos/novo
# ─────────────────────────────────────────
@router.post("/equipas/{equipa_id}/macrociclos/novo")
async def criar_macrociclo(
    equipa_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
    planeamento_anual_equipa_id: str = Form(""),
    data_inicio: str = Form(...),
    data_fim: str = Form(...),
    objetivos_gerais: str = Form(""),
    objetivos_ofensivos: str = Form(""),
    objetivos_defensivos: str = Form(""),
    obj_fisicos: str = Form(""),
    obj_psicologicos: str = Form(""),
):
    _verificar_acesso_planeamento(utilizador, equipa_id, db)

    equipa = db.query(Equipa).filter(Equipa.id == equipa_id).first()
    if not equipa:
        return RedirectResponse(url="/equipas", status_code=303)
    inicio = date.fromisoformat(data_inicio)
    fim = date.fromisoformat(data_fim)
    planeamento_anual = None
    if planeamento_anual_equipa_id:
        planeamento_anual = db.query(PlaneamentoAnualEquipa).filter(
            PlaneamentoAnualEquipa.id == int(planeamento_anual_equipa_id),
            PlaneamentoAnualEquipa.equipa_id == equipa_id,
        ).first()
    if not planeamento_anual:
        planeamento_anual = _obter_ou_criar_anual_equipa(db, equipa, inicio, fim)
    if inicio < planeamento_anual.data_inicio or fim > planeamento_anual.data_fim:
        set_flash(request, "O macrociclo tem de ficar dentro das datas do planeamento anual.", "erro")
        return RedirectResponse(
            url=f"/planeamento/equipas/{equipa_id}/macrociclos/novo?anual_id={planeamento_anual.id}",
            status_code=303,
        )

    total_macros = db.query(Macrociclo).filter(
        Macrociclo.planeamento_anual_equipa_id == planeamento_anual.id,
    ).count()

    macrociclo = Macrociclo(
        numero=total_macros + 1,
        data_inicio=inicio,
        data_fim=fim,
        objetivos_gerais=objetivos_gerais or None,
        objetivos_ofensivos=objetivos_ofensivos or None,
        objetivos_defensivos=objetivos_defensivos or None,
        obj_fisicos=obj_fisicos or None,
        obj_psicologicos=obj_psicologicos or None,
        equipa_id=equipa_id,
        planeamento_anual_equipa_id=planeamento_anual.id,
    )

    # db.add() prepara o objecto para ser inserido na BD
    db.add(macrociclo)
    db.flush()
    renumerar_macrociclos(db, equipa_id, planeamento_anual.id)
    # db.commit() confirma a transacção — só aqui os dados são realmente guardados
    db.commit()

    set_flash(request, "Macrociclo criado com sucesso.")
    return RedirectResponse(url=f"/planeamento/anuais/{planeamento_anual.id}", status_code=303)


# ─────────────────────────────────────────
# DETALHE DE UM MACROCICLO
# URL: GET /planeamento/macrociclos/{macro_id}
# ─────────────────────────────────────────
@router.get("/macrociclos/{macro_id}", response_class=HTMLResponse)
def detalhe_macrociclo(macro_id: int, request: Request, db: Session = Depends(get_db),
                       utilizador=Depends(exigir_autenticacao)):
    _verificar_acesso_planeamento(utilizador, _obter_equipa_id_por_macrociclo(db, macro_id), db)

    macrociclo = db.query(Macrociclo).filter(Macrociclo.id == macro_id).first()
    if not macrociclo:
        return RedirectResponse(url="/equipas")

    # Procura os mesociclos deste macrociclo ordenados pelo número
    mesociclos = db.query(Mesociclo).filter(
        Mesociclo.macrociclo_id == macro_id
    ).order_by(Mesociclo.numero).all()

    # Calcula o próximo número de mesociclo
    proximo_numero_meso = len(mesociclos) + 1
    dashboard_planeamento = obter_dashboard_planeamento_equipa(
        db,
        macrociclo.equipa_id,
        macrociclo.data_inicio,
        macrociclo.data_fim,
    )

    return templates.TemplateResponse(request, "planeamento/macrociclos/detalhe.html", {
        "utilizador": utilizador,
        "macrociclo": macrociclo,
        "planeamento_anual_equipa": macrociclo.planeamento_anual_equipa,
        "mesociclos": mesociclos,
        "proximo_numero_meso": proximo_numero_meso,
        "dashboard_planeamento": dashboard_planeamento,
        "objetivos_por_categoria": objetivos_por_categoria(macrociclo),
        "agenda_contexto": _contexto_agenda(
            equipa_id=macrociclo.equipa_id,
            data_inicio=macrociclo.data_inicio,
            data_fim=macrociclo.data_fim,
            macrociclo_id=macrociclo.id,
        ),
        "agenda_tipos": tipos_agenda_formulario(),
        "espacos_agenda": db.query(EspacoTreino).filter(EspacoTreino.ativo.is_(True)).order_by(EspacoTreino.nome).all(),
    })


@router.get("/macrociclos/{macro_id}/pdf")
def exportar_pdf_macrociclo(
    macro_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    """Exporta o macrociclo com objetivos, balanço e agenda integrada."""
    equipa_id = _obter_equipa_id_por_macrociclo(db, macro_id)
    _verificar_acesso_planeamento(utilizador, equipa_id, db)
    macrociclo = db.query(Macrociclo).filter(Macrociclo.id == macro_id).first()
    if not macrociclo:
        return RedirectResponse(url="/equipas")

    mesociclos = db.query(Mesociclo).filter(
        Mesociclo.macrociclo_id == macro_id
    ).order_by(Mesociclo.numero).all()
    dashboard_planeamento = obter_dashboard_planeamento_equipa(
        db,
        macrociclo.equipa_id,
        macrociclo.data_inicio,
        macrociclo.data_fim,
    )
    pdf_bytes = renderizar_pdf(request, "planeamento/macrociclos/pdf.html", {
        "utilizador": utilizador,
        "macrociclo": macrociclo,
        "mesociclos": mesociclos,
        "dashboard_planeamento": dashboard_planeamento,
        "objetivos_por_categoria": objetivos_por_categoria(macrociclo),
        "hoje": date.today(),
    })
    nome = f"macrociclo_{macrociclo.numero}_{macrociclo.equipa.nome}_{macrociclo.data_inicio}.pdf".replace(" ", "_")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={nome}"},
    )


# ─────────────────────────────────────────
# EDITAR MACROCICLO
# ─────────────────────────────────────────
@router.get("/macrociclos/{macro_id}/editar", response_class=HTMLResponse)
def form_editar_macrociclo(macro_id: int, request: Request, db: Session = Depends(get_db),
                           utilizador=Depends(exigir_autenticacao)):
    _verificar_acesso_planeamento(utilizador, _obter_equipa_id_por_macrociclo(db, macro_id), db)
    macrociclo = db.query(Macrociclo).filter(Macrociclo.id == macro_id).first()
    if not macrociclo:
        return RedirectResponse(url="/equipas")
    equipa = db.query(Equipa).filter(Equipa.id == macrociclo.equipa_id).first()
    return templates.TemplateResponse(request, "planeamento/macrociclos/form.html", {
        "utilizador": utilizador,
        "equipa": equipa,
        "macrociclo": macrociclo,
        "planeamento_anual_equipa": macrociclo.planeamento_anual_equipa,
    })


@router.post("/macrociclos/{macro_id}/editar")
async def editar_macrociclo(
    macro_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
    data_inicio: str = Form(...),
    data_fim: str = Form(...),
    objetivos_gerais: str = Form(""),
    objetivos_ofensivos: str = Form(""),
    objetivos_defensivos: str = Form(""),
    obj_fisicos: str = Form(""),
    obj_psicologicos: str = Form(""),
):
    _verificar_acesso_planeamento(utilizador, _obter_equipa_id_por_macrociclo(db, macro_id), db)
    macrociclo = db.query(Macrociclo).filter(Macrociclo.id == macro_id).first()
    if not macrociclo:
        return RedirectResponse(url="/equipas")
    inicio = date.fromisoformat(data_inicio)
    fim = date.fromisoformat(data_fim)
    if macrociclo.planeamento_anual_equipa and (
        inicio < macrociclo.planeamento_anual_equipa.data_inicio
        or fim > macrociclo.planeamento_anual_equipa.data_fim
    ):
        set_flash(request, "O macrociclo tem de ficar dentro das datas do planeamento anual.", "erro")
        return RedirectResponse(url=f"/planeamento/macrociclos/{macro_id}/editar", status_code=303)
    macrociclo.data_inicio = inicio
    macrociclo.data_fim = fim
    macrociclo.objetivos_gerais = objetivos_gerais or None
    macrociclo.objetivos_ofensivos = objetivos_ofensivos or None
    macrociclo.objetivos_defensivos = objetivos_defensivos or None
    macrociclo.obj_tecnica_individual_ofensiva = None
    macrociclo.obj_tecnica_individual_defensiva = None
    macrociclo.obj_tatica_individual_ofensiva = None
    macrociclo.obj_tatica_individual_defensiva = None
    macrociclo.obj_tatica_coletiva_ofensiva = None
    macrociclo.obj_tatica_coletiva_defensiva = None
    macrociclo.obj_fisicos = obj_fisicos or None
    macrociclo.obj_psicologicos = obj_psicologicos or None
    renumerar_macrociclos(db, macrociclo.equipa_id, macrociclo.planeamento_anual_equipa_id)
    db.commit()
    set_flash(request, "Macrociclo atualizado.")
    return RedirectResponse(url=f"/planeamento/macrociclos/{macro_id}", status_code=303)


@router.post("/macrociclos/{macro_id}/eliminar")
async def eliminar_macrociclo(macro_id: int, request: Request, db: Session = Depends(get_db),
                               utilizador=Depends(exigir_autenticacao)):
    equipa_id = _obter_equipa_id_por_macrociclo(db, macro_id)
    _verificar_acesso_planeamento(utilizador, equipa_id, db)
    macrociclo = db.query(Macrociclo).filter(Macrociclo.id == macro_id).first()
    anual_id = macrociclo.planeamento_anual_equipa_id if macrociclo else None
    if macrociclo:
        db.delete(macrociclo)
        db.flush()
        renumerar_macrociclos(db, equipa_id, anual_id)
        db.commit()
        set_flash(request, "Macrociclo eliminado.")
    retorno = f"/planeamento/anuais/{anual_id}" if anual_id else f"/planeamento/equipas/{equipa_id}/anuais"
    return RedirectResponse(url=retorno, status_code=303)


# ─────────────────────────────────────────
# CRIAR MESOCICLO
# URL: POST /planeamento/macrociclos/{macro_id}/mesociclos/novo
# ─────────────────────────────────────────
@router.post("/macrociclos/{macro_id}/mesociclos/novo")
async def criar_mesociclo(
    macro_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
    data_inicio: str = Form(...),
    data_fim: str = Form(...),
    objetivos_gerais: str = Form(""),
    objetivos_ofensivos: str = Form(""),
    objetivos_defensivos: str = Form(""),
    obj_fisicos: str = Form(""),
    obj_psicologicos: str = Form(""),
):
    _verificar_acesso_planeamento(utilizador, _obter_equipa_id_por_macrociclo(db, macro_id), db)

    # Conta os mesociclos existentes neste macrociclo
    total_mesos = db.query(Mesociclo).filter(
        Mesociclo.macrociclo_id == macro_id
    ).count()

    mesociclo = Mesociclo(
        numero=total_mesos + 1,
        data_inicio=date.fromisoformat(data_inicio),
        data_fim=date.fromisoformat(data_fim),
        objetivos_gerais=objetivos_gerais or None,
        objetivos_ofensivos=objetivos_ofensivos or None,
        objetivos_defensivos=objetivos_defensivos or None,
        obj_fisicos=obj_fisicos or None,
        obj_psicologicos=obj_psicologicos or None,
        macrociclo_id=macro_id
    )

    db.add(mesociclo)
    db.flush()
    renumerar_mesociclos(db, macro_id)
    db.commit()
    set_flash(request, "Mesociclo criado com sucesso.")
    return RedirectResponse(url=f"/planeamento/macrociclos/{macro_id}", status_code=303)


# ─────────────────────────────────────────
# DETALHE DE UM MESOCICLO
# URL: GET /planeamento/mesociclos/{meso_id}
# ─────────────────────────────────────────
@router.get("/mesociclos/{meso_id}", response_class=HTMLResponse)
def detalhe_mesociclo(meso_id: int, request: Request, db: Session = Depends(get_db),
                      utilizador=Depends(exigir_autenticacao)):
    equipa_id = _obter_equipa_id_por_mesociclo(db, meso_id)
    _verificar_acesso_planeamento(utilizador, equipa_id, db)

    mesociclo = db.query(Mesociclo).filter(Mesociclo.id == meso_id).first()
    if not mesociclo:
        return RedirectResponse(url="/equipas")

    microciclos = db.query(Microciclo).filter(
        Microciclo.mesociclo_id == meso_id
    ).order_by(Microciclo.numero).all()

    # Jogos da equipa no período do mesociclo
    jogos_periodo = db.query(Jogo).filter(
        Jogo.equipa_id == equipa_id,
        Jogo.data >= mesociclo.data_inicio,
        Jogo.data <= mesociclo.data_fim,
    ).order_by(Jogo.data).all()

    # IDs de jogos já importados como sessão neste mesociclo
    sessao_datas_jogo = set()
    for micro in microciclos:
        for s in micro.sessoes:
            if s.e_jogo:
                sessao_datas_jogo.add(s.data)

    jogos_nao_importados = [j for j in jogos_periodo if j.data not in sessao_datas_jogo]

    # Dados para gráfico Chart.js (volume e RPE por microciclo)
    chart_labels = []
    chart_volume = []
    chart_rpe = []
    for micro in microciclos:
        sessoes_ativas = [s for s in micro.sessoes if s.ativa]
        volume = sum(s.volume_minutos or 0 for s in sessoes_ativas)
        rpelist = [s.intensidade_rpe for s in sessoes_ativas if s.intensidade_rpe is not None]
        rpe = round(sum(rpelist) / len(rpelist), 1) if rpelist else 0
        chart_labels.append(f"Micro {micro.numero}")
        chart_volume.append(volume)
        chart_rpe.append(rpe)

    # Calendário: semanas cobrindo o intervalo do mesociclo
    cal_start = mesociclo.data_inicio - timedelta(days=mesociclo.data_inicio.weekday())
    cal_end = mesociclo.data_fim + timedelta(days=6 - mesociclo.data_fim.weekday())

    eventos_por_dia: dict[date, list] = {}
    for micro in microciclos:
        for sessao in micro.sessoes:
            if not sessao.ativa:
                continue
            eventos_por_dia.setdefault(sessao.data, []).append({
                "tipo": "jogo" if sessao.e_jogo else "treino",
                "label": f"T{sessao.numero_treino}" if sessao.numero_treino else ("🏀" if sessao.e_jogo else "Treino"),
                "micro_numero": micro.numero,
                "id": sessao.id,
                "link": f"/treino/sessoes/{sessao.id}",
            })
    for jogo in jogos_nao_importados:
        eventos_por_dia.setdefault(jogo.data, []).append({
            "tipo": "jogo_ext",
            "label": f"🏀 {jogo.adversario}",
            "jogo_id": jogo.id,
            "link": f"/jogos/{jogo.id}",
        })

    semanas_calendario = []
    cur = cal_start
    while cur <= cal_end:
        semana = []
        for i in range(7):
            d = cur + timedelta(days=i)
            semana.append({
                "data": d,
                "no_meso": mesociclo.data_inicio <= d <= mesociclo.data_fim,
                "eventos": eventos_por_dia.get(d, []),
            })
        semanas_calendario.append(semana)
        cur += timedelta(days=7)

    proximo_numero_micro = len(microciclos) + 1
    dashboard_planeamento = obter_dashboard_planeamento_equipa(
        db,
        equipa_id,
        mesociclo.data_inicio,
        mesociclo.data_fim,
    )

    return templates.TemplateResponse(request, "planeamento/mesociclos/detalhe.html", {
        "utilizador": utilizador,
        "mesociclo": mesociclo,
        "microciclos": microciclos,
        "proximo_numero_micro": proximo_numero_micro,
        "jogos_periodo": jogos_periodo,
        "jogos_nao_importados": jogos_nao_importados,
        "semanas_calendario": semanas_calendario,
        "chart_labels": json.dumps(chart_labels),
        "chart_volume": json.dumps(chart_volume),
        "chart_rpe": json.dumps(chart_rpe),
        "equipa_id": equipa_id,
        "dashboard_planeamento": dashboard_planeamento,
        "objetivos_por_categoria": objetivos_por_categoria(mesociclo),
        "objetivos_superiores": contexto_objetivos_superiores(
            macrociclo=mesociclo.macrociclo,
        ),
        "agenda_contexto": _contexto_agenda(
            equipa_id=equipa_id,
            data_inicio=mesociclo.data_inicio,
            data_fim=mesociclo.data_fim,
            macrociclo_id=mesociclo.macrociclo_id,
            mesociclo_id=mesociclo.id,
        ),
        "agenda_tipos": tipos_agenda_formulario(),
        "espacos_agenda": db.query(EspacoTreino).filter(EspacoTreino.ativo.is_(True)).order_by(EspacoTreino.nome).all(),
    })


# ─────────────────────────────────────────
# EXPORTAR MESOCICLO EM PDF
# ─────────────────────────────────────────
@router.get("/mesociclos/{meso_id}/pdf")
def exportar_pdf_mesociclo(meso_id: int, request: Request, db: Session = Depends(get_db),
                            utilizador=Depends(exigir_autenticacao)):
    equipa_id = _obter_equipa_id_por_mesociclo(db, meso_id)
    _verificar_acesso_planeamento(utilizador, equipa_id, db)

    mesociclo = db.query(Mesociclo).filter(Mesociclo.id == meso_id).first()
    if not mesociclo:
        return RedirectResponse(url="/equipas")

    equipa = mesociclo.macrociclo.equipa
    microciclos = db.query(Microciclo).filter(
        Microciclo.mesociclo_id == meso_id
    ).order_by(Microciclo.numero).all()

    jogos_periodo = db.query(Jogo).filter(
        Jogo.equipa_id == equipa_id,
        Jogo.data >= mesociclo.data_inicio,
        Jogo.data <= mesociclo.data_fim,
    ).order_by(Jogo.data).all()

    sessao_datas_jogo = set()
    for micro in microciclos:
        for s in micro.sessoes:
            if s.e_jogo:
                sessao_datas_jogo.add(s.data)

    jogos_nao_importados_datas = {j.data for j in jogos_periodo if j.data not in sessao_datas_jogo}

    total_sessoes = sum(1 for m in microciclos for s in m.sessoes if s.ativa and not s.e_jogo)
    vol_total = sum(s.volume_minutos or 0 for m in microciclos for s in m.sessoes if s.ativa)
    vol_total_h = f"{round(vol_total/60,1)}h" if vol_total >= 60 else f"{vol_total}min"
    rpes_meso = [
        s.intensidade_rpe
        for m in microciclos
        for s in m.sessoes
        if s.ativa and not s.e_jogo and s.intensidade_rpe is not None
    ]
    media_rpe = round(sum(rpes_meso) / len(rpes_meso), 1) if rpes_meso else 0

    vol_por_micro = [
        sum(s.volume_minutos or 0 for s in m.sessoes if s.ativa)
        for m in microciclos
    ]
    vol_max = max(vol_por_micro) if vol_por_micro else 1

    pdf_bytes = renderizar_pdf(request, "planeamento/mesociclos/pdf.html", {
        "utilizador": utilizador,
        "mesociclo": mesociclo,
        "equipa": equipa,
        "microciclos": microciclos,
        "jogos_periodo": jogos_periodo,
        "jogos_nao_importados_datas": jogos_nao_importados_datas,
        "total_sessoes": total_sessoes,
        "vol_total_h": vol_total_h,
        "vol_max": vol_max,
        "media_rpe": media_rpe,
        "dashboard_planeamento": obter_dashboard_planeamento_equipa(
            db,
            equipa_id,
            mesociclo.data_inicio,
            mesociclo.data_fim,
        ),
        "objetivos_por_categoria": objetivos_por_categoria(mesociclo),
        "objetivos_superiores": contexto_objetivos_superiores(macrociclo=mesociclo.macrociclo),
        "hoje": date.today(),
    })

    nome = f"mesociclo_{mesociclo.numero}_{equipa.nome}_{mesociclo.data_inicio}.pdf"
    nome_safe = nome.replace(" ", "_")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={nome_safe}"},
    )


# ─────────────────────────────────────────
# EDITAR MESOCICLO
# ─────────────────────────────────────────
@router.get("/mesociclos/{meso_id}/editar", response_class=HTMLResponse)
def form_editar_mesociclo(meso_id: int, request: Request, db: Session = Depends(get_db),
                          utilizador=Depends(exigir_autenticacao)):
    _verificar_acesso_planeamento(utilizador, _obter_equipa_id_por_mesociclo(db, meso_id), db)
    mesociclo = db.query(Mesociclo).filter(Mesociclo.id == meso_id).first()
    if not mesociclo:
        return RedirectResponse(url="/equipas")
    return templates.TemplateResponse(request, "planeamento/mesociclos/form.html", {
        "utilizador": utilizador,
        "mesociclo": mesociclo,
    })


@router.post("/mesociclos/{meso_id}/editar")
async def editar_mesociclo(
    meso_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
    data_inicio: str = Form(...),
    data_fim: str = Form(...),
    objetivos_gerais: str = Form(""),
    objetivos_ofensivos: str = Form(""),
    objetivos_defensivos: str = Form(""),
    obj_fisicos: str = Form(""),
    obj_psicologicos: str = Form(""),
):
    _verificar_acesso_planeamento(utilizador, _obter_equipa_id_por_mesociclo(db, meso_id), db)
    mesociclo = db.query(Mesociclo).filter(Mesociclo.id == meso_id).first()
    if not mesociclo:
        return RedirectResponse(url="/equipas")
    mesociclo.data_inicio = date.fromisoformat(data_inicio)
    mesociclo.data_fim = date.fromisoformat(data_fim)
    mesociclo.objetivos_gerais = objetivos_gerais or None
    mesociclo.objetivos_ofensivos = objetivos_ofensivos or None
    mesociclo.objetivos_defensivos = objetivos_defensivos or None
    mesociclo.obj_tecnica_individual_ofensiva = None
    mesociclo.obj_tecnica_individual_defensiva = None
    mesociclo.obj_tatica_individual_ofensiva = None
    mesociclo.obj_tatica_individual_defensiva = None
    mesociclo.obj_tatica_coletiva_ofensiva = None
    mesociclo.obj_tatica_coletiva_defensiva = None
    mesociclo.obj_fisicos = obj_fisicos or None
    mesociclo.obj_psicologicos = obj_psicologicos or None
    renumerar_mesociclos(db, mesociclo.macrociclo_id)
    db.commit()
    set_flash(request, "Mesociclo atualizado.")
    return RedirectResponse(url=f"/planeamento/mesociclos/{meso_id}", status_code=303)


@router.post("/mesociclos/{meso_id}/eliminar")
async def eliminar_mesociclo(meso_id: int, request: Request, db: Session = Depends(get_db),
                              utilizador=Depends(exigir_autenticacao)):
    macro_id = None
    mesociclo = db.query(Mesociclo).filter(Mesociclo.id == meso_id).first()
    if mesociclo:
        macro_id = mesociclo.macrociclo_id
        db.delete(mesociclo)
        db.flush()
        renumerar_mesociclos(db, macro_id)
        db.commit()
        set_flash(request, "Mesociclo eliminado.")
    return RedirectResponse(url=f"/planeamento/macrociclos/{macro_id}" if macro_id else "/equipas", status_code=303)


# ─────────────────────────────────────────
# IMPORTAR JOGO COMO SESSÃO NO MESOCICLO
# URL: POST /planeamento/mesociclos/{meso_id}/importar-jogo/{jogo_id}
# ─────────────────────────────────────────
@router.post("/mesociclos/{meso_id}/importar-jogo/{jogo_id}")
async def importar_jogo_como_sessao(meso_id: int, jogo_id: int, request: Request,
                                     db: Session = Depends(get_db),
                                     utilizador=Depends(exigir_autenticacao)):
    equipa_id = _obter_equipa_id_por_mesociclo(db, meso_id)
    _verificar_acesso_planeamento(utilizador, equipa_id, db)

    jogo = db.query(Jogo).filter(Jogo.id == jogo_id, Jogo.equipa_id == equipa_id).first()
    if not jogo:
        set_flash(request, "Jogo não encontrado.", "error")
        return RedirectResponse(url=f"/planeamento/mesociclos/{meso_id}", status_code=303)

    microciclo = db.query(Microciclo).filter(
        Microciclo.mesociclo_id == meso_id,
        Microciclo.data_inicio <= jogo.data,
        Microciclo.data_fim >= jogo.data,
    ).first()

    if not microciclo:
        set_flash(request, f"Nenhum microciclo cobre a data do jogo ({jogo.data}). Cria primeiro o microciclo.", "error")
        return RedirectResponse(url=f"/planeamento/mesociclos/{meso_id}", status_code=303)

    # Calcula próximo número de treino na época para esta equipa
    from sqlalchemy import func as sqlfunc
    max_num = db.query(sqlfunc.max(SessaoTreino.numero_treino)).join(
        Microciclo, SessaoTreino.microciclo_id == Microciclo.id
    ).join(Mesociclo, Microciclo.mesociclo_id == Mesociclo.id).join(
        Macrociclo, Mesociclo.macrociclo_id == Macrociclo.id
    ).filter(Macrociclo.equipa_id == equipa_id).scalar() or 0

    sessao = SessaoTreino(
        data=jogo.data,
        local=jogo.local,
        hora_inicio=normalizar_hora(jogo.hora),
        e_jogo=True,
        origem="jogo",
        microciclo_id=microciclo.id,
        numero_treino=max_num + 1,
        ativa=True,
    )
    db.add(sessao)
    db.commit()
    set_flash(request, f"Jogo vs {jogo.adversario} importado como sessão no Micro {microciclo.numero}.")
    return RedirectResponse(url=f"/planeamento/mesociclos/{meso_id}", status_code=303)


# ─────────────────────────────────────────
# GUARDAR REFLEXÃO DO MESOCICLO
# ─────────────────────────────────────────
@router.post("/mesociclos/{meso_id}/reflexao")
async def guardar_reflexao_mesociclo(meso_id: int, request: Request,
                                      db: Session = Depends(get_db),
                                      utilizador=Depends(exigir_autenticacao),
                                      reflexao: str = Form("")):
    _verificar_acesso_planeamento(utilizador, _obter_equipa_id_por_mesociclo(db, meso_id), db)
    mesociclo = db.query(Mesociclo).filter(Mesociclo.id == meso_id).first()
    if mesociclo:
        mesociclo.reflexao = reflexao or None
        db.commit()
        set_flash(request, "Reflexão guardada.")
    return RedirectResponse(url=f"/planeamento/mesociclos/{meso_id}", status_code=303)


# ─────────────────────────────────────────
# CRIAR MICROCICLO
# URL: POST /planeamento/mesociclos/{meso_id}/microciclos/novo
# ─────────────────────────────────────────
@router.post("/mesociclos/{meso_id}/microciclos/novo")
async def criar_microciclo(
    meso_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
    data_inicio: str = Form(...),
    data_fim: str = Form(...),
    tipo: str = Form(""),
    objetivos_gerais: str = Form(""),
    objetivos_ofensivos: str = Form(""),
    objetivos_defensivos: str = Form(""),
    obj_fisicos: str = Form(""),
    obj_psicologicos: str = Form(""),
):
    _verificar_acesso_planeamento(utilizador, _obter_equipa_id_por_mesociclo(db, meso_id), db)

    total_micros = db.query(Microciclo).filter(
        Microciclo.mesociclo_id == meso_id
    ).count()

    microciclo = Microciclo(
        numero=total_micros + 1,
        data_inicio=date.fromisoformat(data_inicio),
        data_fim=date.fromisoformat(data_fim),
        tipo=tipo or None,
        objetivos_gerais=objetivos_gerais or None,
        objetivos_ofensivos=objetivos_ofensivos or None,
        objetivos_defensivos=objetivos_defensivos or None,
        obj_fisicos=obj_fisicos or None,
        obj_psicologicos=obj_psicologicos or None,
        mesociclo_id=meso_id
    )

    db.add(microciclo)
    db.flush()
    renumerar_microciclos(db, meso_id)
    eventos_integrados = _integrar_eventos_planeados_no_microciclo(db, microciclo)
    db.commit()
    mensagem = "Microciclo criado com sucesso."
    if eventos_integrados:
        mensagem += f" Foram integrados {eventos_integrados} treino(s) ou jogo(s) já marcados no planeamento."
    set_flash(request, mensagem)
    return RedirectResponse(
        url=f"/planeamento/mesociclos/{meso_id}",
        status_code=303
    )


# ─────────────────────────────────────────
# EDITAR MICROCICLO
# ─────────────────────────────────────────
@router.get("/microciclos/{micro_id}/editar", response_class=HTMLResponse)
def form_editar_microciclo(micro_id: int, request: Request, db: Session = Depends(get_db),
                           utilizador=Depends(exigir_autenticacao)):
    _verificar_acesso_planeamento(utilizador, _obter_equipa_id_por_microciclo(db, micro_id), db)
    microciclo = db.query(Microciclo).filter(Microciclo.id == micro_id).first()
    if not microciclo:
        return RedirectResponse(url="/equipas")
    return templates.TemplateResponse(request, "planeamento/microciclos/form.html", {
        "utilizador": utilizador,
        "microciclo": microciclo,
    })


@router.post("/microciclos/{micro_id}/editar")
async def editar_microciclo(
    micro_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
    data_inicio: str = Form(...),
    data_fim: str = Form(...),
    tipo: str = Form(""),
    objetivos_gerais: str = Form(""),
    objetivos_ofensivos: str = Form(""),
    objetivos_defensivos: str = Form(""),
    obj_fisicos: str = Form(""),
    obj_psicologicos: str = Form(""),
):
    _verificar_acesso_planeamento(utilizador, _obter_equipa_id_por_microciclo(db, micro_id), db)
    microciclo = db.query(Microciclo).filter(Microciclo.id == micro_id).first()
    if not microciclo:
        return RedirectResponse(url="/equipas")
    microciclo.data_inicio = date.fromisoformat(data_inicio)
    microciclo.data_fim = date.fromisoformat(data_fim)
    microciclo.tipo = tipo or None
    microciclo.objetivos_gerais = objetivos_gerais or None
    microciclo.objetivos_ofensivos = objetivos_ofensivos or None
    microciclo.objetivos_defensivos = objetivos_defensivos or None
    microciclo.obj_tecnica_individual_ofensiva = None
    microciclo.obj_tecnica_individual_defensiva = None
    microciclo.obj_tatica_individual_ofensiva = None
    microciclo.obj_tatica_individual_defensiva = None
    microciclo.obj_tatica_coletiva_ofensiva = None
    microciclo.obj_tatica_coletiva_defensiva = None
    microciclo.obj_fisicos = obj_fisicos or None
    microciclo.obj_psicologicos = obj_psicologicos or None
    renumerar_microciclos(db, microciclo.mesociclo_id)
    db.commit()
    set_flash(request, "Microciclo atualizado.")
    return RedirectResponse(url=f"/planeamento/microciclos/{micro_id}", status_code=303)


@router.post("/microciclos/{micro_id}/eliminar")
async def eliminar_microciclo(micro_id: int, request: Request, db: Session = Depends(get_db),
                               utilizador=Depends(exigir_autenticacao)):
    meso_id = None
    microciclo = db.query(Microciclo).filter(Microciclo.id == micro_id).first()
    if microciclo:
        meso_id = microciclo.mesociclo_id
        db.delete(microciclo)
        db.flush()
        renumerar_microciclos(db, meso_id)
        db.commit()
        set_flash(request, "Microciclo eliminado.")
    return RedirectResponse(url=f"/planeamento/mesociclos/{meso_id}" if meso_id else "/equipas", status_code=303)


# ─────────────────────────────────────────
# DETALHE DE UM MICROCICLO
# URL: GET /planeamento/microciclos/{micro_id}
# ─────────────────────────────────────────
@router.get("/microciclos/{micro_id}", response_class=HTMLResponse)
def detalhe_microciclo(micro_id: int, request: Request, db: Session = Depends(get_db),
                       utilizador=Depends(exigir_autenticacao)):
    equipa_id = _obter_equipa_id_por_microciclo(db, micro_id)
    _verificar_acesso_planeamento(utilizador, equipa_id, db)

    microciclo = db.query(Microciclo).filter(Microciclo.id == micro_id).first()
    if not microciclo:
        return RedirectResponse(url="/equipas")

    from models.planeamento import SessaoTreino
    filtro_sessoes = request.query_params.get("filtro_sessoes", "todas")
    if filtro_sessoes not in {"todas", "manuais", "planeamento_global", "alteradas_manual", "desatualizadas"}:
        filtro_sessoes = "todas"

    sessoes = db.query(SessaoTreino).filter(
        SessaoTreino.microciclo_id == micro_id,
    ).order_by(SessaoTreino.data, SessaoTreino.id).all()
    sessoes = _ordenar_sessoes_microciclo(sessoes)
    sessoes = preparar_sessoes_para_ui(sessoes)
    sessoes_filtradas = [sessao for sessao in sessoes if sessao_corresponde_filtro(sessao, filtro_sessoes)]
    sessoes_ativas = [sessao for sessao in sessoes if sessao.ativa]
    calendario_semanal = _construir_calendario_microciclo(sessoes_ativas)
    balanco, dados_graficos = _calcular_balanco_microciclo(sessoes_ativas)

    filtros_sessoes = [
        {"valor": "todas", "label": "Todas", "total": len(sessoes)},
        {"valor": "manuais", "label": "Manuais", "total": len([s for s in sessoes if s.origem != "planeamento_global"])},
        {"valor": "planeamento_global", "label": "Planeamento global", "total": len([s for s in sessoes if s.origem == "planeamento_global"])},
        {"valor": "alteradas_manual", "label": "Alteradas manualmente", "total": len([s for s in sessoes if s.alterada_manual])},
        {
            "valor": "desatualizadas",
            "label": "Desatualizadas",
            "total": len([
                s for s in sessoes
                if s.origem == "planeamento_global"
                and not s.alterada_manual
                and not s.sincronizada
                and s.ativa
            ]),
        },
    ]

    aviso_divergencia_atribuicao = None
    if request.query_params.get("divergencia_atribuicao") == "1":
        aviso_divergencia_atribuicao = {
            "mensagem": request.query_params.get("mensagem") or "A sessão foi criada com divergência face à atribuição global.",
            "atribuicao_local": request.query_params.get("atribuicao_local"),
            "atribuicao_hora_inicio": request.query_params.get("atribuicao_hora_inicio"),
            "atribuicao_hora_fim": request.query_params.get("atribuicao_hora_fim"),
            "sessao_local": request.query_params.get("sessao_local"),
            "sessao_data": request.query_params.get("sessao_data"),
        }

    return templates.TemplateResponse(request, "planeamento/microciclos/detalhe.html", {
        "utilizador": utilizador,
        "microciclo": microciclo,
        "equipa": microciclo.mesociclo.macrociclo.equipa,
        "sessoes": sessoes_filtradas,
        "treinos_conteudos": [
            sessao for sessao in sessoes_ativas if not sessao.e_jogo
        ],
        "categorias_conteudo": categorias_conteudo_para_ui(),
        "categorias_conteudo_por_codigo": CATEGORIAS_POR_CODIGO,
        "visao_semanal_conteudos": construir_visao_semanal_conteudos(
            microciclo.data_inicio,
            microciclo.data_fim,
            [sessao for sessao in sessoes_ativas if not sessao.e_jogo],
        ),
        "calendario_semanal": calendario_semanal,
        "filtro_sessoes_atual": filtro_sessoes,
        "filtros_sessoes": filtros_sessoes,
        "dados_graficos": dados_graficos,
        "aviso_divergencia_atribuicao": aviso_divergencia_atribuicao,
        # Passamos o balanço para o template
        "balanco": balanco,
        "dashboard_planeamento": obter_dashboard_planeamento_equipa(
            db,
            equipa_id,
            microciclo.data_inicio,
            microciclo.data_fim,
        ),
        "objetivos_por_categoria": objetivos_por_categoria(microciclo),
        "objetivos_superiores": contexto_objetivos_superiores(
            macrociclo=microciclo.mesociclo.macrociclo,
            mesociclo=microciclo.mesociclo,
        ),
        "agenda_contexto": _contexto_agenda(
            equipa_id=equipa_id,
            data_inicio=microciclo.data_inicio,
            data_fim=microciclo.data_fim,
            macrociclo_id=microciclo.mesociclo.macrociclo_id,
            mesociclo_id=microciclo.mesociclo_id,
            microciclo_id=microciclo.id,
        ),
        "agenda_tipos": tipos_agenda_formulario(),
        "espacos_agenda": db.query(EspacoTreino).filter(EspacoTreino.ativo.is_(True)).order_by(EspacoTreino.nome).all(),
    })
# ─────────────────────────────────────────
# CRIAR SESSÃO DE TREINO
# URL: POST /planeamento/microciclos/{micro_id}/sessoes/nova
# ─────────────────────────────────────────
@router.post("/microciclos/{micro_id}/sessoes/nova")
async def criar_sessao(
    micro_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
    data: str = Form(...),
    local: str = Form(""),
    hora_inicio: str = Form(""),
    hora_fim: str = Form(""),
    volume_minutos: str = Form(""),
    intensidade_rpe: str = Form(""),
    e_jogo: str = Form("")
):
    equipa_id = _obter_equipa_id_por_microciclo(db, micro_id)
    _verificar_acesso_planeamento(utilizador, equipa_id, db)

    from models.planeamento import SessaoTreino
    microciclo = db.query(Microciclo).filter(Microciclo.id == micro_id).first()
    if not microciclo:
        return RedirectResponse(url="/equipas", status_code=303)

    erro_horario = _validar_intervalo_horario_sessao(hora_inicio or None, hora_fim or None)
    if erro_horario:
        set_flash(request, erro_horario, "error")
        return RedirectResponse(url=f"/planeamento/microciclos/{micro_id}", status_code=303)
    hora_inicio = normalizar_hora(hora_inicio)
    hora_fim = normalizar_hora(hora_fim)

    total_treinos = db.query(SessaoTreino).filter(
        SessaoTreino.microciclo_id == micro_id,
        SessaoTreino.e_jogo == False,
        SessaoTreino.ativa == True,
    ).count()

    data_sessao = date.fromisoformat(data)

    if data_sessao < microciclo.data_inicio or data_sessao > microciclo.data_fim:
        set_flash(request, "A data da sessão tem de estar dentro do intervalo do microciclo.", "error")
        return RedirectResponse(url=f"/planeamento/microciclos/{micro_id}", status_code=303)

    divergencia_atribuicao = _verificar_divergencia_atribuicao(
        db=db,
        sessao_data=data_sessao,
        equipa_id=equipa_id,
        local_planeado=local,
    )

    sessao = SessaoTreino(
        data=data_sessao,
        local=local or None,
        hora_inicio=hora_inicio,
        hora_fim=hora_fim,
        volume_minutos=int(volume_minutos) if volume_minutos else None,
        intensidade_rpe=float(intensidade_rpe) if intensidade_rpe else None,
        e_jogo=e_jogo == "true",
        numero_treino=None if e_jogo == "true" else total_treinos + 1,
        microciclo_id=micro_id
    )

    db.add(sessao)
    db.commit()

    if divergencia_atribuicao["divergente"]:
        atribuicao = divergencia_atribuicao["atribuicao"]
        query_string = urlencode({
            "divergencia_atribuicao": "1",
            "mensagem": divergencia_atribuicao["mensagem"] or "",
            "atribuicao_local": atribuicao.espaco.nome if atribuicao and atribuicao.espaco else "",
            "atribuicao_hora_inicio": atribuicao.hora_inicio if atribuicao else "",
            "atribuicao_hora_fim": atribuicao.hora_fim if atribuicao else "",
            "sessao_local": local or "",
            "sessao_data": data_sessao.isoformat(),
        })
        return RedirectResponse(
            url=f"/planeamento/microciclos/{micro_id}?{query_string}",
            status_code=303
        )

    return RedirectResponse(
        url=f"/planeamento/microciclos/{micro_id}",
        status_code=303
    )


@router.post("/microciclos/{micro_id}/sessoes/{sessao_id}/carga")
async def atualizar_carga_rapida_sessao(
    micro_id: int,
    sessao_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
    volume_minutos: str = Form(""),
    intensidade_rpe: str = Form(""),
):
    """Atualiza a previsão de carga diretamente na agenda do microciclo."""
    equipa_id = _obter_equipa_id_por_microciclo(db, micro_id)
    _verificar_acesso_planeamento(utilizador, equipa_id, db)
    sessao = db.query(SessaoTreino).filter(
        SessaoTreino.id == sessao_id,
        SessaoTreino.microciclo_id == micro_id,
        SessaoTreino.ativa.is_(True),
    ).first()
    if not sessao:
        return RedirectResponse(url=f"/planeamento/microciclos/{micro_id}", status_code=303)
    try:
        volume = int(volume_minutos)
        rpe = float(intensidade_rpe)
        if not 1 <= volume <= 600 or not 0 <= rpe <= 10:
            raise ValueError
    except (TypeError, ValueError):
        set_flash(request, "Indica um volume entre 1 e 600 minutos e um RPE entre 0 e 10.", "error")
        return RedirectResponse(url=f"/planeamento/microciclos/{micro_id}", status_code=303)
    sessao.volume_minutos = volume
    sessao.intensidade_rpe = rpe
    sessao.alterada_manual = True
    sessao.sincronizada = False
    db.commit()
    set_flash(request, "Volume e RPE atualizados.")
    return RedirectResponse(url=f"/planeamento/microciclos/{micro_id}", status_code=303)


@router.post("/microciclos/{micro_id}/sessoes/{sessao_id}/conteudos")
async def adicionar_conteudo_sessao(
    micro_id: int,
    sessao_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
    categoria: str = Form(...),
    descricao: str = Form(...),
    minutos: str = Form(...),
):
    """Adiciona um conteúdo planeado ao treino sem alterar a sua agenda."""
    equipa_id = _obter_equipa_id_por_microciclo(db, micro_id)
    _verificar_acesso_planeamento(utilizador, equipa_id, db)
    sessao = db.query(SessaoTreino).filter(
        SessaoTreino.id == sessao_id,
        SessaoTreino.microciclo_id == micro_id,
        SessaoTreino.e_jogo.is_(False),
        SessaoTreino.ativa.is_(True),
    ).first()
    if not sessao:
        return RedirectResponse(url=f"/planeamento/microciclos/{micro_id}", status_code=303)

    descricao = descricao.strip()
    try:
        minutos_int = int(minutos)
        if categoria not in CATEGORIAS_POR_CODIGO or not descricao or not 1 <= minutos_int <= 600:
            raise ValueError
    except (TypeError, ValueError):
        set_flash(request, "Indica uma categoria, conteúdo e duração entre 1 e 600 minutos.", "error")
        return RedirectResponse(url=f"/planeamento/microciclos/{micro_id}", status_code=303)

    ordem = len(sessao.conteudos) + 1
    sessao.conteudos.append(ConteudoSessaoTreino(
        categoria=categoria,
        descricao=descricao,
        minutos=minutos_int,
        ordem=ordem,
    ))
    atualizar_minutos_por_componente(sessao)
    sessao.alterada_manual = True
    sessao.sincronizada = False
    db.commit()
    set_flash(request, "Conteúdo adicionado ao treino.")
    return RedirectResponse(url=f"/planeamento/microciclos/{micro_id}", status_code=303)


@router.post("/microciclos/{micro_id}/sessoes/{sessao_id}/conteudos/{conteudo_id}/eliminar")
async def eliminar_conteudo_sessao(
    micro_id: int,
    sessao_id: int,
    conteudo_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    equipa_id = _obter_equipa_id_por_microciclo(db, micro_id)
    _verificar_acesso_planeamento(utilizador, equipa_id, db)
    sessao = db.query(SessaoTreino).filter(
        SessaoTreino.id == sessao_id,
        SessaoTreino.microciclo_id == micro_id,
        SessaoTreino.e_jogo.is_(False),
        SessaoTreino.ativa.is_(True),
    ).first()
    conteudo = db.query(ConteudoSessaoTreino).filter(
        ConteudoSessaoTreino.id == conteudo_id,
        ConteudoSessaoTreino.sessao_id == sessao_id,
    ).first()
    if not sessao or not conteudo:
        return RedirectResponse(url=f"/planeamento/microciclos/{micro_id}", status_code=303)

    # Remover pela relação mantém a coleção em memória sincronizada antes do recálculo.
    sessao.conteudos.remove(conteudo)
    db.flush()
    atualizar_minutos_por_componente(sessao)
    sessao.alterada_manual = True
    sessao.sincronizada = False
    db.commit()
    set_flash(request, "Conteúdo removido do treino.")
    return RedirectResponse(url=f"/planeamento/microciclos/{micro_id}", status_code=303)


@router.get("/microciclos/{micro_id}/calendario/pdf")
def exportar_pdf_calendario_microciclo(
    micro_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    equipa_id = _obter_equipa_id_por_microciclo(db, micro_id)
    _verificar_acesso_planeamento(utilizador, equipa_id, db)

    microciclo = db.query(Microciclo).filter(Microciclo.id == micro_id).first()
    if not microciclo:
        return RedirectResponse(url="/equipas")

    equipa = microciclo.mesociclo.macrociclo.equipa
    sessoes_ativas = [sessao for sessao in _ordenar_sessoes_microciclo(list(microciclo.sessoes)) if sessao.ativa]
    calendario_semanal = _construir_calendario_microciclo(sessoes_ativas)

    pdf_bytes = renderizar_pdf(request, "planeamento/microciclos/calendario_pdf.html", {
        "utilizador": utilizador,
        "microciclo": microciclo,
        "equipa": equipa,
        "calendario_semanal": calendario_semanal,
        "total_treinos_calendario": len([sessao for sessao in sessoes_ativas if not sessao.e_jogo]),
        "total_jogos_calendario": len([sessao for sessao in sessoes_ativas if sessao.e_jogo]),
        "hoje": date.today(),
    })

    nome = f"calendario_microciclo_{microciclo.numero}_{equipa.nome}.pdf".replace(" ", "_")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={nome}"},
    )


@router.get("/microciclos/{micro_id}/pdf")
def exportar_pdf_microciclo(
    micro_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    equipa_id = _obter_equipa_id_por_microciclo(db, micro_id)
    _verificar_acesso_planeamento(utilizador, equipa_id, db)

    microciclo = db.query(Microciclo).filter(Microciclo.id == micro_id).first()
    if not microciclo:
        return RedirectResponse(url="/equipas")

    equipa = microciclo.mesociclo.macrociclo.equipa
    sessoes_ativas = [sessao for sessao in _ordenar_sessoes_microciclo(list(microciclo.sessoes)) if sessao.ativa]
    calendario_semanal = _construir_calendario_microciclo(sessoes_ativas)
    balanco, dados_graficos = _calcular_balanco_microciclo(sessoes_ativas)
    resumo_assiduidade = _calcular_resumo_assiduidade_microciclo(db, equipa.id, sessoes_ativas)

    sessoes_pdf = []
    for sessao in sessoes_ativas:
        plano = sessao.plano_treino
        sessoes_pdf.append({
            "sessao": sessao,
            "plano": plano,
            "dia_semana": _obter_nome_dia_semana(sessao.data),
            "intervalo_horario": _formatar_intervalo_sessao(sessao),
            "tipo_label": _obter_tipo_legivel_sessao(sessao),
            "exercicios_por_bloco": _agrupar_exercicios_por_bloco(plano),
        })

    pdf_bytes = renderizar_pdf(request, "planeamento/microciclos/pdf.html", {
        "utilizador": utilizador,
        "microciclo": microciclo,
        "equipa": equipa,
        "calendario_semanal": calendario_semanal,
        "sessoes_pdf": sessoes_pdf,
        "balanco": balanco,
        "dados_graficos": dados_graficos,
        "resumo_assiduidade": resumo_assiduidade,
        "dashboard_planeamento": obter_dashboard_planeamento_equipa(
            db,
            equipa.id,
            microciclo.data_inicio,
            microciclo.data_fim,
        ),
        "objetivos_por_categoria": objetivos_por_categoria(microciclo),
        "objetivos_superiores": contexto_objetivos_superiores(
            macrociclo=microciclo.mesociclo.macrociclo,
            mesociclo=microciclo.mesociclo,
        ),
        "hoje": date.today(),
    })

    nome = f"microciclo_{microciclo.numero}_{equipa.nome}_{microciclo.data_inicio}.pdf".replace(" ", "_")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={nome}"},
    )

# ─────────────────────────────────────────
# GUARDAR REFLEXÃO DO MICROCICLO
# URL: POST /planeamento/microciclos/{micro_id}/reflexao
# ─────────────────────────────────────────
@router.post("/microciclos/{micro_id}/reflexao")
async def guardar_reflexao_microciclo(
    micro_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
    reflexao: str = Form("")
):
    equipa_id = _obter_equipa_id_por_microciclo(db, micro_id)
    _verificar_acesso_planeamento(utilizador, equipa_id, db)

    # Procura o microciclo na base de dados
    microciclo = db.query(Microciclo).filter(Microciclo.id == micro_id).first()
    if not microciclo:
        return RedirectResponse(url="/equipas")

    # Actualiza apenas o campo reflexao
    # Não precisamos de criar um novo objecto — modificamos o existente
    microciclo.reflexao = reflexao or None

    db.commit()
    set_flash(request, "Reflexão guardada.")
    return RedirectResponse(
        url=f"/planeamento/microciclos/{micro_id}",
        status_code=303
    )


@router.get("/microciclos/{micro_id}/excel")
def exportar_excel_microciclo(
    micro_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    equipa_id = _obter_equipa_id_por_microciclo(db, micro_id)
    _verificar_acesso_planeamento(utilizador, equipa_id, db)

    from models.planeamento import Microciclo, SessaoTreino
    from models.assiduidade import RegistoAssiduidade
    from models.jogador import Jogador
    from models.jogo import Jogo

    # Procura o microciclo pelo ID
    microciclo = db.query(Microciclo).filter(Microciclo.id == micro_id).first()
    if not microciclo:
        return RedirectResponse(url="/equipas")

    # Navega na hierarquia para chegar à equipa:
    # microciclo -> mesociclo -> macrociclo -> equipa
    equipa = microciclo.mesociclo.macrociclo.equipa

    # Procura todas as sessões deste microciclo, ordenadas por data
    sessoes = db.query(SessaoTreino).filter(
        SessaoTreino.microciclo_id == micro_id,
        SessaoTreino.ativa == True,
    ).order_by(SessaoTreino.data).all()

    # Separa treinos e jogos
    treinos = [s for s in sessoes if not s.e_jogo]
    sessoes_jogo = [s for s in sessoes if s.e_jogo]

    # --------------------------------------------------
    # ESTATÍSTICAS GERAIS DO MICROCICLO
    # --------------------------------------------------

    # Volume total = soma dos minutos de treino
    volume_total = sum(s.volume_minutos or 0 for s in treinos)

    # Média RPE = média das sessões com RPE preenchido
    rpes_validos = [s.intensidade_rpe for s in treinos if s.intensidade_rpe is not None]
    media_rpe = round(sum(rpes_validos) / len(rpes_validos), 1) if rpes_validos else 0

    # Tempo por componente técnico-tática/física
    componentes = {
        "TIO": sum(s.min_tecnica_individual_ofensiva or 0 for s in treinos),
        "TID": sum(s.min_tecnica_individual_defensiva or 0 for s in treinos),
        "TaIO": sum(s.min_tatica_individual_ofensiva or 0 for s in treinos),
        "TaID": sum(s.min_tatica_individual_defensiva or 0 for s in treinos),
        "TCO": sum(s.min_tatica_coletiva_ofensiva or 0 for s in treinos),
        "TCD": sum(s.min_tatica_coletiva_defensiva or 0 for s in treinos),
        "Físicos": sum(s.min_fisicos or 0 for s in treinos),
    }

    # --------------------------------------------------
    # ESTATÍSTICAS COMPETITIVAS
    # --------------------------------------------------
    # No teu modelo, os resultados estão na tabela Jogo.
    # Como as sessões de treino/jogo do microciclo não estão ligadas
    # diretamente à tabela Jogo, vamos considerar os jogos da equipa
    # dentro do intervalo de datas do microciclo.
    jogos_equipa_micro = db.query(Jogo).filter(
        Jogo.equipa_id == equipa.id,
        Jogo.data >= microciclo.data_inicio,
        Jogo.data <= microciclo.data_fim
    ).order_by(Jogo.data).all()

    jogos_previstos = len(jogos_equipa_micro)

    jogos_realizados = len([
        j for j in jogos_equipa_micro
        if j.pontos_nos is not None and j.pontos_adversario is not None
    ])

    vitorias = len([
        j for j in jogos_equipa_micro
        if j.pontos_nos is not None
        and j.pontos_adversario is not None
        and j.pontos_nos > j.pontos_adversario
    ])

    derrotas = len([
        j for j in jogos_equipa_micro
        if j.pontos_nos is not None
        and j.pontos_adversario is not None
        and j.pontos_nos < j.pontos_adversario
    ])

    pontos_marcados = sum(j.pontos_nos or 0 for j in jogos_equipa_micro)
    pontos_sofridos = sum(j.pontos_adversario or 0 for j in jogos_equipa_micro)

    # --------------------------------------------------
    # ASSIDUIDADE POR ATLETA
    # --------------------------------------------------
    jogadores = db.query(Jogador).filter(
        Jogador.equipa_id == equipa.id
    ).order_by(Jogador.nome).all()

    # Sessões de treino contam para assiduidade.
    # Normalmente não contamos sessões marcadas como jogo.
    sessoes_treino_ids = [s.id for s in treinos]

    assiduidade_jogadores = []

    for jogador in jogadores:
        # Registos de assiduidade deste jogador nas sessões de treino do microciclo
        registos = db.query(RegistoAssiduidade).filter(
            RegistoAssiduidade.jogador_id == jogador.id,
            RegistoAssiduidade.sessao_id.in_(sessoes_treino_ids) if sessoes_treino_ids else False
        ).all() if sessoes_treino_ids else []

        total_registos = len(registos)
        presencas = sum(1 for r in registos if r.presente)
        faltas = total_registos - presencas
        percentagem = round((presencas / total_registos) * 100, 1) if total_registos > 0 else 0

        assiduidade_jogadores.append({
            "jogador": jogador,
            "presencas": presencas,
            "faltas": faltas,
            "percentagem": percentagem
        })

    # Percentagem média global da equipa
    percentagens_validas = [a["percentagem"] for a in assiduidade_jogadores]
    percentagem_presencas_equipa = (
        round(sum(percentagens_validas) / len(percentagens_validas), 1)
        if percentagens_validas else 0
    )

    # Lesões:
    # neste momento ainda não existe um modelo específico para lesões,
    # por isso deixamos o valor a 0 como placeholder.
    lesoes = 0

    # --------------------------------------------------
    # CRIAÇÃO DO EXCEL
    # --------------------------------------------------
    wb = Workbook()
    ws = wb.active
    ws.title = "Balanço Microciclo"

    # Estilos simples para dar melhor aspeto ao ficheiro
    cor_titulo = "E25A1C"   # laranja principal
    fill_titulo = PatternFill("solid", fgColor=cor_titulo)
    fill_secao = PatternFill("solid", fgColor="F3F4F6")  # cinzento claro
    fonte_titulo = Font(color="FFFFFF", bold=True, size=12)
    fonte_secao = Font(bold=True)
    fonte_bold = Font(bold=True)
    alinhamento_centro = Alignment(horizontal="center", vertical="center")

    # Função auxiliar para escrever títulos de secção
    def escrever_secao(linha: int, texto: str):
        ws[f"A{linha}"] = texto
        ws[f"A{linha}"].font = fonte_titulo
        ws[f"A{linha}"].fill = fill_titulo
        ws[f"A{linha}"].alignment = alinhamento_centro
        ws.merge_cells(f"A{linha}:D{linha}")

    linha = 1

    # --------------------------------------------------
    # SECÇÃO 1 — IDENTIFICAÇÃO
    # --------------------------------------------------
    escrever_secao(linha, "Balanço do Microciclo")
    linha += 2

    ws[f"A{linha}"] = "Equipa"
    ws[f"B{linha}"] = equipa.nome
    linha += 1

    ws[f"A{linha}"] = "Microciclo"
    ws[f"B{linha}"] = microciclo.numero
    linha += 1

    ws[f"A{linha}"] = "Período"
    ws[f"B{linha}"] = f"{microciclo.data_inicio} a {microciclo.data_fim}"
    linha += 1

    ws[f"A{linha}"] = "Tipo"
    ws[f"B{linha}"] = microciclo.tipo or "—"
    linha += 2

    # --------------------------------------------------
    # SECÇÃO 2 — RESUMO COMPETITIVO
    # --------------------------------------------------
    escrever_secao(linha, "Resumo Competitivo")
    linha += 2

    dados_competicao = [
        ("Jogos previstos", jogos_previstos),
        ("Jogos realizados", jogos_realizados),
        ("Vitórias", vitorias),
        ("Derrotas", derrotas),
        ("Pontos marcados", pontos_marcados),
        ("Pontos sofridos", pontos_sofridos),
    ]

    for label, valor in dados_competicao:
        ws[f"A{linha}"] = label
        ws[f"B{linha}"] = valor
        linha += 1

    linha += 1

    # --------------------------------------------------
    # SECÇÃO 3 — RESUMO DO TREINO
    # --------------------------------------------------
    escrever_secao(linha, "Resumo do Treino")
    linha += 2

    dados_treino = [
        ("Treinos previstos", len(treinos)),
        ("Treinos realizados", len(treinos)),
        ("% presenças média da equipa", percentagem_presencas_equipa),
        ("Média RPE", media_rpe),
        ("Volume total (min)", volume_total),
        ("Lesões", lesoes),
    ]

    for label, valor in dados_treino:
        ws[f"A{linha}"] = label
        ws[f"B{linha}"] = valor
        linha += 1

    linha += 1

    # --------------------------------------------------
    # SECÇÃO 4 — TEMPO POR COMPONENTE
    # --------------------------------------------------
    escrever_secao(linha, "Tempo por Componente")
    linha += 2

    for componente, minutos in componentes.items():
        ws[f"A{linha}"] = componente
        ws[f"B{linha}"] = minutos
        linha += 1

    linha += 1

    # --------------------------------------------------
    # SECÇÃO 5 — ASSIDUIDADE POR ATLETA
    # --------------------------------------------------
    escrever_secao(linha, "Assiduidade por Atleta")
    linha += 2

    cabecalhos = ["Jogador", "Presenças", "Faltas", "% Presença"]
    for col, texto in enumerate(cabecalhos, start=1):
        celula = ws.cell(row=linha, column=col)
        celula.value = texto
        celula.font = fonte_secao
        celula.fill = fill_secao
        celula.alignment = alinhamento_centro

    linha += 1

    for item in assiduidade_jogadores:
        jogador = item["jogador"]

        ws[f"A{linha}"] = jogador.nome
        ws[f"B{linha}"] = item["presencas"]
        ws[f"C{linha}"] = item["faltas"]
        ws[f"D{linha}"] = item["percentagem"]
        linha += 1

    # --------------------------------------------------
    # SECÇÃO 6 — SESSÕES DO MICROCICLO
    # --------------------------------------------------
    linha += 1
    escrever_secao(linha, "Sessões do Microciclo")
    linha += 2

    cabecalhos_sessoes = ["Data", "Tipo", "Nº Treino", "Local", "Volume", "RPE"]
    for col, texto in enumerate(cabecalhos_sessoes, start=1):
        celula = ws.cell(row=linha, column=col)
        celula.value = texto
        celula.font = fonte_secao
        celula.fill = fill_secao
        celula.alignment = alinhamento_centro

    linha += 1

    for sessao in sessoes:
        ws[f"A{linha}"] = str(sessao.data)
        ws[f"B{linha}"] = "Jogo" if sessao.e_jogo else "Treino"
        ws[f"C{linha}"] = sessao.numero_treino if sessao.numero_treino is not None else "—"
        ws[f"D{linha}"] = sessao.local or "—"
        ws[f"E{linha}"] = sessao.volume_minutos if sessao.volume_minutos is not None else 0
        ws[f"F{linha}"] = sessao.intensidade_rpe if sessao.intensidade_rpe is not None else 0
        linha += 1

    # --------------------------------------------------
    # AJUSTE DE LARGURAS DE COLUNA
    # --------------------------------------------------
    larguras = {
        "A": 28,
        "B": 18,
        "C": 14,
        "D": 18,
        "E": 12,
        "F": 10,
    }

    for coluna, largura in larguras.items():
        ws.column_dimensions[coluna].width = largura

    # Coloca em bold a primeira coluna das secções simples
    for row in ws.iter_rows():
        if row[0].value and row[0].row > 1:
            # Mantemos os títulos principais já formatados e
            # destacamos labels simples
            if isinstance(row[0].value, str) and row[0].value not in [
                "Balanço do Microciclo",
                "Resumo Competitivo",
                "Resumo do Treino",
                "Tempo por Componente",
                "Assiduidade por Atleta",
                "Sessões do Microciclo",
                "Jogador",
                "Presenças",
                "Faltas",
                "% Presença",
                "Data",
                "Tipo",
                "Nº Treino",
                "Local",
                "Volume",
                "RPE",
            ]:
                row[0].font = fonte_bold

    # --------------------------------------------------
    # GUARDA O FICHEIRO EM MEMÓRIA
    # --------------------------------------------------
    ficheiro = BytesIO()
    wb.save(ficheiro)
    ficheiro.seek(0)

    # Nome do ficheiro para o download
    nome_ficheiro = f"balanco_microciclo_{microciclo.numero}_{equipa.nome}.xlsx".replace(" ", "_")

    # StreamingResponse envia o ficheiro sem o guardar no disco
    return StreamingResponse(
        ficheiro,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{nome_ficheiro}"'
        }
    )

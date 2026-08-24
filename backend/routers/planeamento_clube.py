import calendar
import re
from datetime import date, datetime, timedelta
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from template_config import Jinja2Templates
from sqlalchemy.orm import Session

from auth import verificar_perfil
from auth_deps import exigir_coordenacao, exigir_operacao_desportiva, exigir_secretaria
from flash import set_flash
from database import get_db
from horarios import hora_eh_anterior, hora_valida, normalizar_hora
from models.atividade import Atividade
from models.atribuicao_espaco_semanal import (
    AtribuicaoEspacoSemanal,
    EstadoAtribuicaoEspacoEnum,
    OrigemAtribuicaoEspacoEnum,
    TipoOcupacaoEspacoEnum,
)
from models.equipa import Equipa
from models.espaco_treino import (
    DisponibilidadeEspacoTreino,
    EspacoTreino,
    IndisponibilidadeEspacoTreino,
    TipoEspacoTreinoEnum,
)
from models.jogo import Jogo
from models.historico_planeamento import HistoricoPlaneamentoClube
from models.indisponibilidade_treinador import IndisponibilidadeTreinador
from models.planeamento import Macrociclo, Mesociclo, Microciclo, PlaneamentoAnualEquipa, SessaoTreino
from models.planeamento_clube import (
    EventoPlaneamentoClube,
    OrigemEventoPlaneamentoClubeEnum,
    PlaneamentoClubeAnual,
    PlaneamentoClubeMensal,
    PlanoSemanalClube,
    TipoEventoPlaneamentoClubeEnum,
)
from models.treinador import Treinador
from paths import TEMPLATES_DIR
from services.operacao_clube_service import (
    construir_mapa_espacos_semanal,
    obter_resumo_operacional_mensal,
)
from services.planeamento_semanal_administrativo_service import gerar_grelha_slots, validar_reserva
from services.atribuicao_espaco_agenda_service import sincronizar_atribuicao_com_agenda
from services.notificacoes_service import criar_notificacoes_para_equipa
from services.atribuicao_espaco_visual_service import (
    COR_NEUTRA,
    construir_cores_espacos,
    construir_cores_equipas,
    construir_quadro_atribuicoes,
)
from services.auditoria_service import registar_auditoria
from services.agenda_service import metadados_tipo_agenda, tipos_agenda_formulario
from services.historico_planeamento_service import registar_historico_planeamento
from services.planeamento_integrado_service import obter_dashboard_planeamento_anual
from services.numeracao_planeamento_service import (
    renumerar_macrociclos,
    renumerar_mesociclos,
    renumerar_microciclos,
    renumerar_treinos_equipa,
)
from services.pdf_service import renderizar_pdf
from services.sincronizacao_ui import (
    construir_resumo_sincronizacao_texto,
    formatar_data_hora,
    preparar_sessoes_para_ui,
)

router = APIRouter(prefix="/planeamento-clube")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

MENSAGENS_ERRO_ELIMINACAO = {
    "anual_com_mensais": "Não é possível eliminar este planeamento anual porque existem planeamentos mensais associados.",
    "anual_com_eventos": "Não é possível eliminar este planeamento anual porque existem eventos globais associados diretamente.",
    "mensal_com_semanais": "Não é possível eliminar este planeamento mensal porque existem planos semanais associados.",
    "mensal_com_eventos": "Não é possível eliminar este planeamento mensal porque existem eventos globais associados diretamente.",
    "semanal_com_dependencias": "Não é possível eliminar este plano semanal porque existem eventos ou atribuições de espaço associados.",
    "espaco_com_atribuicoes": "Não é possível eliminar este espaço porque existem atribuições semanais associadas.",
}

ESTADOS_PLANEAMENTO = {"rascunho", "ativo"}


def _destino_retorno_seguro(request: Request, retorno: str | None, fallback: str) -> str:
    """Mantem a acao no ecrã de origem, sem aceitar redirecionamentos externos."""
    candidatos = (retorno, request.headers.get("referer"))
    for candidato in candidatos:
        if not candidato:
            continue
        partes = urlsplit(candidato)
        if partes.scheme or partes.netloc:
            if partes.netloc != request.url.netloc:
                continue
        if partes.path.startswith("/") and not partes.path.startswith("//"):
            return partes.path + (f"?{partes.query}" if partes.query else "")
    return fallback


def _obter_conflitos_publicacao(db: Session, semanal: PlanoSemanalClube) -> list[dict]:
    atribuicoes = db.query(AtribuicaoEspacoSemanal).filter(
        AtribuicaoEspacoSemanal.plano_semanal_id == semanal.id,
        AtribuicaoEspacoSemanal.estado != EstadoAtribuicaoEspacoEnum.cancelado,
    ).all()
    return construir_mapa_espacos_semanal(atribuicoes)["conflitos"]


def _normalizar_estado_planeamento(estado: str | None) -> str:
    valor = (estado or "rascunho").strip().lower()
    if valor not in ESTADOS_PLANEAMENTO:
        raise ValueError("O estado do planeamento deve ser rascunho ou ativo.")
    return valor


def _converter_data(valor: str | None, nome: str) -> date:
    try:
        return date.fromisoformat((valor or "").strip())
    except (TypeError, ValueError):
        raise ValueError(f"{nome} inválida. Indica uma data válida.") from None


def _validar_intervalo_datas(
    data_inicio: str | None,
    data_fim: str | None,
    nome: str,
) -> tuple[date, date]:
    inicio = _converter_data(data_inicio, f"Data de início do {nome}")
    fim = _converter_data(data_fim, f"Data de fim do {nome}")
    if inicio > fim:
        raise ValueError(f"A data de início do {nome} não pode ser posterior à data de fim.")
    return inicio, fim


def _validar_ano_mes(ano: str | int, mes: str | int) -> tuple[int, int]:
    try:
        ano_convertido = int(ano)
        mes_convertido = int(mes)
    except (TypeError, ValueError):
        raise ValueError("Ano e mês têm de ser valores numéricos válidos.") from None
    if ano_convertido < 1 or ano_convertido > 9999:
        raise ValueError("O ano indicado não é válido.")
    if mes_convertido < 1 or mes_convertido > 12:
        raise ValueError("O mês indicado deve estar entre 1 e 12.")
    return ano_convertido, mes_convertido


def _normalizar_horas_evento(
    hora_inicio: str | None,
    hora_fim: str | None,
) -> tuple[str | None, str | None]:
    inicio = normalizar_hora(hora_inicio) if hora_inicio else None
    fim = normalizar_hora(hora_fim) if hora_fim else None
    if hora_inicio and inicio is None:
        raise ValueError("A hora de início não é válida. Usa o formato HH:MM.")
    if hora_fim and fim is None:
        raise ValueError("A hora de término não é válida. Usa o formato HH:MM.")
    if inicio and fim and not hora_eh_anterior(inicio, fim):
        raise ValueError("A hora de início deve ser anterior à hora de término.")
    return inicio, fim


def _normalizar_enum(valor: str | None, enum_cls, nome: str) -> str:
    valor_normalizado = (valor or "").strip()
    permitidos = {item.value for item in enum_cls}
    if valor_normalizado not in permitidos:
        opcoes = ", ".join(sorted(permitidos))
        raise ValueError(f"{nome} inválido. Valores permitidos: {opcoes}.")
    return valor_normalizado


def _normalizar_capacidade(capacidade: str | int | None) -> int | None:
    if capacidade in (None, ""):
        return None
    try:
        valor = int(capacidade)
    except (TypeError, ValueError):
        raise ValueError("A capacidade deve ser um número inteiro.") from None
    if valor < 1:
        raise ValueError("A capacidade deve ser superior a zero.")
    return valor


def _converter_id(valor: str | int | None, nome: str, *, obrigatorio: bool = False) -> int | None:
    if valor in (None, ""):
        if obrigatorio:
            raise ValueError(f"{nome} é obrigatório.")
        return None
    try:
        convertido = int(valor)
    except (TypeError, ValueError):
        raise ValueError(f"{nome} inválido.") from None
    if convertido < 1:
        raise ValueError(f"{nome} inválido.")
    return convertido


def _responder_pdf(request: Request, nome_template: str, contexto: dict, nome_ficheiro: str) -> Response:
    """Renderiza um template de impressão como PDF A4."""
    pdf_bytes = renderizar_pdf(request, nome_template, contexto)
    nome_seguro = re.sub(r"[^A-Za-z0-9._-]+", "_", nome_ficheiro)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={nome_seguro}"},
    )




def _obter_estado_visual_plano_semanal(semanal: PlanoSemanalClube) -> dict[str, str]:
    """Traduz o estado do plano semanal para um badge simples."""
    if semanal.estado == "ativo":
        return {"label": "Ativo", "classes": "bg-emerald-100 text-emerald-800"}
    return {"label": "Rascunho", "classes": "bg-amber-100 text-amber-800"}


def _formatar_intervalo_calendario(hora_inicio: str | None, hora_fim: str | None) -> str:
    """Gera um texto curto de horário para os cartões do calendário."""
    if hora_inicio and hora_fim:
        return f"{hora_inicio}-{hora_fim}"
    if hora_inicio:
        return hora_inicio
    if hora_fim:
        return f"até {hora_fim}"
    return "Dia inteiro"


def _listar_eventos_ordenados(db: Session):
    """Obtém os eventos do planeamento global ordenados por data e hora."""
    return db.query(EventoPlaneamentoClube).order_by(
        EventoPlaneamentoClube.data.desc(),
        EventoPlaneamentoClube.hora_inicio.desc(),
    ).all()


def _obter_contexto_form_evento(db: Session):
    """Reúne dados auxiliares para o formulário de evento."""
    return {
        "tipos_evento": TipoEventoPlaneamentoClubeEnum,
        "tipos_evento_agenda": tipos_agenda_formulario(),
        "origens_evento": OrigemEventoPlaneamentoClubeEnum,
        "planeamentos_anuais": db.query(PlaneamentoClubeAnual).order_by(PlaneamentoClubeAnual.data_inicio.desc()).all(),
        "planeamentos_mensais": db.query(PlaneamentoClubeMensal).order_by(
            PlaneamentoClubeMensal.ano.desc(),
            PlaneamentoClubeMensal.mes.desc(),
        ).all(),
        "planos_semanais": db.query(PlanoSemanalClube).order_by(PlanoSemanalClube.data_inicio.desc()).all(),
        "equipas": db.query(Equipa).order_by(Equipa.nome).all(),
        "espacos": db.query(EspacoTreino).order_by(EspacoTreino.nome).all(),
        "treinadores": db.query(Treinador).order_by(Treinador.nome).all(),
        "jogos": db.query(Jogo).order_by(Jogo.data.desc()).all(),
        "atividades": db.query(Atividade).order_by(Atividade.data.desc()).all(),
    }


def _obter_contexto_form_espaco():
    """Reúne dados auxiliares para o formulário de espaço."""
    return {
        "tipos_espaco": TipoEspacoTreinoEnum,
    }


def _obter_contexto_form_anual():
    """Reúne dados auxiliares para o formulário anual."""
    return {}


def _obter_contexto_form_mensal():
    """Reúne dados auxiliares para o formulário mensal."""
    return {
        "estados_mensal": ["rascunho", "ativo"],
    }


def _obter_contexto_form_semanal():
    """Reúne dados auxiliares para o formulário semanal."""
    return {
        "estados_semanal": ["rascunho", "ativo"],
    }


def _obter_contexto_form_atribuicao(db: Session, semanal_id: int | None = None):
    """Reúne dados auxiliares para o formulário de atribuição semanal."""
    query_semanais = db.query(PlanoSemanalClube).order_by(PlanoSemanalClube.data_inicio.desc())
    if semanal_id:
        query_semanais = query_semanais.filter(PlanoSemanalClube.id == semanal_id)

    return {
        "tipos_ocupacao": TipoOcupacaoEspacoEnum,
        "estados_atribuicao": EstadoAtribuicaoEspacoEnum,
        "origens_atribuicao": OrigemAtribuicaoEspacoEnum,
        "espacos": db.query(EspacoTreino).order_by(EspacoTreino.nome).all(),
        "equipas": db.query(Equipa).order_by(Equipa.nome).all(),
        "treinadores": db.query(Treinador).order_by(Treinador.nome).all(),
        "eventos_globais": db.query(EventoPlaneamentoClube).order_by(
            EventoPlaneamentoClube.data.desc(),
            EventoPlaneamentoClube.hora_inicio.desc(),
        ).all(),
        "planos_semanais": query_semanais.all(),
    }


def _criar_espaco(
    nome: str,
    tipo: str,
    localizacao: str,
    capacidade: str,
    ativo: str,
    observacoes: str,
):
    """Constrói um espaço de treino a partir do formulário."""
    return EspacoTreino(
        nome=nome,
        tipo=_normalizar_enum(tipo, TipoEspacoTreinoEnum, "Tipo de espaço"),
        localizacao=localizacao or None,
        capacidade=_normalizar_capacidade(capacidade),
        ativo=ativo == "true",
        observacoes=observacoes or None,
    )


def _criar_planeamento_anual(
    epoca: str,
    titulo: str,
    data_inicio: str,
    data_fim: str,
    objetivos_gerais: str,
    observacoes: str,
    ativo: str,
):
    """Constrói um planeamento anual a partir do formulário."""
    inicio, fim = _validar_intervalo_datas(data_inicio, data_fim, "planeamento anual")
    return PlaneamentoClubeAnual(
        epoca=epoca,
        titulo=titulo,
        data_inicio=inicio,
        data_fim=fim,
        objetivos_gerais=objetivos_gerais or None,
        observacoes=observacoes or None,
        ativo=ativo == "true",
    )


def _atualizar_planeamento_anual(
    planeamento: PlaneamentoClubeAnual,
    epoca: str,
    titulo: str,
    data_inicio: str,
    data_fim: str,
    objetivos_gerais: str,
    observacoes: str,
    ativo: str,
):
    """Actualiza os campos editáveis de um planeamento anual."""
    inicio, fim = _validar_intervalo_datas(data_inicio, data_fim, "planeamento anual")
    planeamento.epoca = epoca
    planeamento.titulo = titulo
    planeamento.data_inicio = inicio
    planeamento.data_fim = fim
    planeamento.objetivos_gerais = objetivos_gerais or None
    planeamento.observacoes = observacoes or None
    planeamento.ativo = ativo == "true"


def _criar_planeamento_mensal(
    anual_id: int,
    ano: str,
    mes: str,
    titulo: str,
    objetivos_mes: str,
    observacoes: str,
    estado: str,
):
    """Constrói um planeamento mensal a partir do formulário."""
    ano_convertido, mes_convertido = _validar_ano_mes(ano, mes)
    return PlaneamentoClubeMensal(
        planeamento_anual_id=anual_id,
        ano=ano_convertido,
        mes=mes_convertido,
        titulo=titulo,
        objetivos_mes=objetivos_mes or None,
        observacoes=observacoes or None,
        estado=_normalizar_estado_planeamento(estado),
    )


def _atualizar_planeamento_mensal(
    mensal: PlaneamentoClubeMensal,
    ano: str,
    mes: str,
    titulo: str,
    objetivos_mes: str,
    observacoes: str,
    estado: str,
):
    """Actualiza os campos editáveis de um planeamento mensal."""
    ano_convertido, mes_convertido = _validar_ano_mes(ano, mes)
    mensal.ano = ano_convertido
    mensal.mes = mes_convertido
    mensal.titulo = titulo
    mensal.objetivos_mes = objetivos_mes or None
    mensal.observacoes = observacoes or None
    mensal.estado = _normalizar_estado_planeamento(estado)


def _criar_plano_semanal_modelo(
    mensal_id: int,
    titulo: str,
    data_inicio: str,
    data_fim: str,
    observacoes: str,
    estado: str,
):
    """Constrói um plano semanal a partir do formulário."""
    inicio, fim = _validar_intervalo_datas(data_inicio, data_fim, "plano semanal")
    return PlanoSemanalClube(
        planeamento_mensal_id=mensal_id,
        titulo=titulo,
        data_inicio=inicio,
        data_fim=fim,
        observacoes=observacoes or None,
        estado=_normalizar_estado_planeamento(estado),
    )


def _atualizar_plano_semanal_modelo(
    semanal: PlanoSemanalClube,
    titulo: str,
    data_inicio: str,
    data_fim: str,
    observacoes: str,
    estado: str,
):
    """Actualiza os campos editáveis de um plano semanal."""
    inicio, fim = _validar_intervalo_datas(data_inicio, data_fim, "plano semanal")
    semanal.titulo = titulo
    semanal.data_inicio = inicio
    semanal.data_fim = fim
    semanal.observacoes = observacoes or None
    semanal.estado = _normalizar_estado_planeamento(estado)


def _atualizar_espaco(
    espaco: EspacoTreino,
    nome: str,
    tipo: str,
    localizacao: str,
    capacidade: str,
    ativo: str,
    observacoes: str,
):
    """Actualiza os campos editáveis de um espaço."""
    espaco.nome = nome
    espaco.tipo = _normalizar_enum(tipo, TipoEspacoTreinoEnum, "Tipo de espaço")
    espaco.localizacao = localizacao or None
    espaco.capacidade = _normalizar_capacidade(capacidade)
    espaco.ativo = ativo == "true"
    espaco.observacoes = observacoes or None


def _preparar_atribuicao_form(
    db: Session,
    utilizador,
    modo: str,
    semanal: PlanoSemanalClube | None,
    atribuicao: AtribuicaoEspacoSemanal | None,
    erro: str | None = None,
    dados_formulario: dict | None = None,
):
    """Monta o contexto comum do formulário de atribuição."""
    contexto = _obter_contexto_form_atribuicao(db, semanal.id if semanal else None)
    contexto.update({
        "utilizador": utilizador,
        "modo": modo,
        "semanal": semanal,
        "atribuicao": atribuicao,
        "erro": erro,
        "dados_formulario": dados_formulario or {},
    })
    return contexto


def _validar_dados_atribuicao(
    semanal: PlanoSemanalClube,
    data_atribuicao: str,
    hora_inicio: str,
    hora_fim: str,
):
    """Valida a coerência base dos campos temporais da atribuição."""
    if not hora_valida(hora_inicio, permitir_vazio=False) or not hora_valida(hora_fim, permitir_vazio=False):
        return "As horas devem estar no formato HH:MM."

    hora_inicio_normalizada = normalizar_hora(hora_inicio, permitir_vazio=False)
    hora_fim_normalizada = normalizar_hora(hora_fim, permitir_vazio=False)
    if not hora_eh_anterior(hora_inicio_normalizada, hora_fim_normalizada):
        return "A hora de fim deve ser posterior à hora de início."

    try:
        data_convertida = date.fromisoformat(data_atribuicao)
    except (TypeError, ValueError):
        return "A data da atribuição não é válida."
    if data_convertida < semanal.data_inicio or data_convertida > semanal.data_fim:
        return "A data da atribuição tem de estar dentro do intervalo do plano semanal."

    return None


def _obter_atribuicao_conflitante(
    db: Session,
    espaco_id: int,
    data_atribuicao: date,
    hora_inicio: str,
    hora_fim: str,
    atribuicao_id_excluir: int | None = None,
):
    """Procura outra atribuição activa sobreposta no mesmo espaço e data."""
    query = db.query(AtribuicaoEspacoSemanal).filter(
        AtribuicaoEspacoSemanal.espaco_id == espaco_id,
        AtribuicaoEspacoSemanal.data == data_atribuicao,
        AtribuicaoEspacoSemanal.estado != EstadoAtribuicaoEspacoEnum.cancelado,
        AtribuicaoEspacoSemanal.hora_inicio < hora_fim,
        AtribuicaoEspacoSemanal.hora_fim > hora_inicio,
    )

    if atribuicao_id_excluir:
        query = query.filter(AtribuicaoEspacoSemanal.id != atribuicao_id_excluir)

    return query.order_by(AtribuicaoEspacoSemanal.hora_inicio).first()


def _criar_atribuicao(
    semanal_id: int,
    espaco_id: str,
    equipa_id: str,
    treinador_id: str,
    evento_id: str,
    data_atribuicao: str,
    hora_inicio: str,
    hora_fim: str,
    tipo_ocupacao: str,
    estado: str,
    origem: str,
    observacoes: str,
):
    """Constrói uma atribuição semanal a partir do formulário."""
    hora_inicio = normalizar_hora(hora_inicio, permitir_vazio=False)
    hora_fim = normalizar_hora(hora_fim, permitir_vazio=False)
    return AtribuicaoEspacoSemanal(
        plano_semanal_id=semanal_id,
        espaco_id=_converter_id(espaco_id, "Espaço", obrigatorio=True),
        equipa_id=_converter_id(equipa_id, "Equipa"),
        treinador_id=_converter_id(treinador_id, "Treinador"),
        evento_id=_converter_id(evento_id, "Evento"),
        data=_converter_data(data_atribuicao, "Data da atribuição"),
        hora_inicio=hora_inicio,
        hora_fim=hora_fim,
        tipo_ocupacao=_normalizar_enum(tipo_ocupacao, TipoOcupacaoEspacoEnum, "Tipo de ocupação"),
        estado=_normalizar_enum(estado, EstadoAtribuicaoEspacoEnum, "Estado da atribuição"),
        origem=_normalizar_enum(origem, OrigemAtribuicaoEspacoEnum, "Origem da atribuição"),
        observacoes=observacoes or None,
    )


def _atualizar_atribuicao(
    atribuicao: AtribuicaoEspacoSemanal,
    semanal_id: int,
    espaco_id: str,
    equipa_id: str,
    treinador_id: str,
    evento_id: str,
    data_atribuicao: str,
    hora_inicio: str,
    hora_fim: str,
    tipo_ocupacao: str,
    estado: str,
    origem: str,
    observacoes: str,
):
    """Actualiza os campos editáveis de uma atribuição semanal."""
    hora_inicio = normalizar_hora(hora_inicio, permitir_vazio=False)
    hora_fim = normalizar_hora(hora_fim, permitir_vazio=False)
    atribuicao.plano_semanal_id = semanal_id
    atribuicao.espaco_id = _converter_id(espaco_id, "Espaço", obrigatorio=True)
    atribuicao.equipa_id = _converter_id(equipa_id, "Equipa")
    atribuicao.treinador_id = _converter_id(treinador_id, "Treinador")
    atribuicao.evento_id = _converter_id(evento_id, "Evento")
    atribuicao.data = _converter_data(data_atribuicao, "Data da atribuição")
    atribuicao.hora_inicio = hora_inicio
    atribuicao.hora_fim = hora_fim
    atribuicao.tipo_ocupacao = _normalizar_enum(tipo_ocupacao, TipoOcupacaoEspacoEnum, "Tipo de ocupação")
    atribuicao.estado = _normalizar_enum(estado, EstadoAtribuicaoEspacoEnum, "Estado da atribuição")
    atribuicao.origem = _normalizar_enum(origem, OrigemAtribuicaoEspacoEnum, "Origem da atribuição")
    atribuicao.observacoes = observacoes or None


def _criar_evento_manual(
    tipo: str,
    titulo: str,
    descricao: str,
    data_evento: str,
    hora_inicio: str,
    hora_fim: str,
    planeamento_anual_id: str,
    planeamento_mensal_id: str,
    plano_semanal_id: str,
    equipa_id: str,
    espaco_id: str,
    treinador_id: str,
    aplica_a_todas_equipas: str,
    observacoes: str,
):
    """Constrói um evento manual a partir do formulário."""
    hora_inicio, hora_fim = _normalizar_horas_evento(hora_inicio, hora_fim)
    return EventoPlaneamentoClube(
        tipo=_normalizar_enum(tipo, TipoEventoPlaneamentoClubeEnum, "Tipo de evento"),
        titulo=titulo,
        descricao=descricao or None,
        data=_converter_data(data_evento, "Data do evento"),
        hora_inicio=hora_inicio,
        hora_fim=hora_fim,
        planeamento_anual_id=_converter_id(planeamento_anual_id, "Planeamento anual"),
        planeamento_mensal_id=_converter_id(planeamento_mensal_id, "Planeamento mensal"),
        plano_semanal_id=_converter_id(plano_semanal_id, "Plano semanal"),
        equipa_id=_converter_id(equipa_id, "Equipa"),
        espaco_id=_converter_id(espaco_id, "Espaço"),
        treinador_id=_converter_id(treinador_id, "Treinador"),
        aplica_a_todas_equipas=aplica_a_todas_equipas == "true",
        origem=OrigemEventoPlaneamentoClubeEnum.manual,
        observacoes=observacoes or None,
    )


def _atualizar_evento(
    evento: EventoPlaneamentoClube,
    tipo: str,
    titulo: str,
    descricao: str,
    data_evento: str,
    hora_inicio: str,
    hora_fim: str,
    planeamento_anual_id: str,
    planeamento_mensal_id: str,
    plano_semanal_id: str,
    equipa_id: str,
    espaco_id: str,
    treinador_id: str,
    aplica_a_todas_equipas: str,
    observacoes: str,
):
    """Actualiza os campos editáveis de um evento."""
    hora_inicio, hora_fim = _normalizar_horas_evento(hora_inicio, hora_fim)
    evento.tipo = _normalizar_enum(tipo, TipoEventoPlaneamentoClubeEnum, "Tipo de evento")
    evento.titulo = titulo
    evento.descricao = descricao or None
    evento.data = _converter_data(data_evento, "Data do evento")
    evento.hora_inicio = hora_inicio
    evento.hora_fim = hora_fim
    evento.planeamento_anual_id = _converter_id(planeamento_anual_id, "Planeamento anual")
    evento.planeamento_mensal_id = _converter_id(planeamento_mensal_id, "Planeamento mensal")
    evento.plano_semanal_id = _converter_id(plano_semanal_id, "Plano semanal")
    evento.equipa_id = _converter_id(equipa_id, "Equipa")
    evento.espaco_id = _converter_id(espaco_id, "Espaço")
    evento.treinador_id = _converter_id(treinador_id, "Treinador")
    evento.aplica_a_todas_equipas = aplica_a_todas_equipas == "true"
    evento.observacoes = observacoes or None


def _obter_titulo_jogo(jogo: Jogo) -> str:
    """Gera um título simples a partir de um jogo."""
    nome_equipa = jogo.equipa.nome if jogo.equipa else "Equipa"
    return f"Jogo {nome_equipa} vs {jogo.adversario}"


def _sincronizar_equipas_evento(db: Session, evento: EventoPlaneamentoClube, equipas_ids: list[str]):
    """Sincroniza as equipas associadas ao evento e mantém o campo legado coerente."""
    if evento.aplica_a_todas_equipas:
        evento.equipas = []
        evento.equipa_id = None
        return

    ids_unicos = []
    for equipa_id in equipas_ids:
        if equipa_id and equipa_id.isdigit():
            ids_unicos.append(int(equipa_id))
    ids_unicos = list(dict.fromkeys(ids_unicos))

    if ids_unicos:
        evento.equipas = db.query(Equipa).filter(Equipa.id.in_(ids_unicos)).order_by(Equipa.nome).all()
        evento.equipa_id = ids_unicos[0]
    else:
        evento.equipas = []
        evento.equipa_id = None


def _conflitos_evento(db: Session, evento: EventoPlaneamentoClube) -> list[str]:
    """Deteta sobreposições operacionais de equipa, treinador e espaço."""
    if not evento.hora_inicio or not evento.hora_fim:
        return []
    query = db.query(EventoPlaneamentoClube).filter(EventoPlaneamentoClube.data == evento.data)
    if evento.id:
        query = query.filter(EventoPlaneamentoClube.id != evento.id)
    equipas_evento = {equipa.id for equipa in evento.equipas}
    if evento.equipa_id:
        equipas_evento.add(evento.equipa_id)
    conflitos = []
    for existente in query.all():
        if not existente.hora_inicio or not existente.hora_fim:
            continue
        if evento.hora_inicio >= existente.hora_fim or evento.hora_fim <= existente.hora_inicio:
            continue
        motivos = []
        equipas_existente = {equipa.id for equipa in existente.equipas}
        if existente.equipa_id:
            equipas_existente.add(existente.equipa_id)
        if evento.aplica_a_todas_equipas or existente.aplica_a_todas_equipas or equipas_evento.intersection(equipas_existente):
            motivos.append("equipa")
        if evento.treinador_id and evento.treinador_id == existente.treinador_id:
            motivos.append("treinador")
        if evento.espaco_id and evento.espaco_id == existente.espaco_id:
            motivos.append("espaço")
        if motivos:
            conflitos.append(f"{existente.titulo} ({', '.join(motivos)})")
    return conflitos


def _evento_visivel_para_equipa(evento: EventoPlaneamentoClube, equipa_id: int) -> bool:
    """Indica se um evento global deve ser apresentado no contexto de uma equipa."""
    if evento.aplica_a_todas_equipas:
        return True

    if evento.equipa_id == equipa_id:
        return True

    return any(equipa.id == equipa_id for equipa in evento.equipas)


def _tipo_evento_gera_sessao(evento: EventoPlaneamentoClube) -> bool:
    """Indica se o evento deve originar uma sessão operacional de equipa."""
    return evento.tipo in {
        TipoEventoPlaneamentoClubeEnum.treino_equipa,
        TipoEventoPlaneamentoClubeEnum.treino_fisico,
        TipoEventoPlaneamentoClubeEnum.treino_individual,
    }


def _obter_equipas_alvo_evento(db: Session, evento: EventoPlaneamentoClube) -> list[Equipa]:
    """Resolve as equipas destino de um evento respeitando as regras de visibilidade."""
    if evento.aplica_a_todas_equipas:
        return db.query(Equipa).order_by(Equipa.nome).all()

    equipas_por_id: dict[int, Equipa] = {}
    if evento.equipa:
        equipas_por_id[evento.equipa.id] = evento.equipa
    for equipa in evento.equipas:
        equipas_por_id[equipa.id] = equipa

    return list(equipas_por_id.values())


def _obter_intervalo_semana(data_evento: date) -> tuple[date, date]:
    """Calcula o intervalo semanal (segunda a domingo) para uma data."""
    data_inicio = data_evento - timedelta(days=data_evento.weekday())
    data_fim = data_inicio + timedelta(days=6)
    return data_inicio, data_fim


def _obter_microciclo_existente_equipa_semana(
    db: Session,
    equipa_id: int,
    data_inicio: date,
    data_fim: date,
) -> Microciclo | None:
    """Procura um microciclo já existente para a mesma equipa e semana."""
    return db.query(Microciclo).join(Mesociclo).join(Macrociclo).filter(
        Macrociclo.equipa_id == equipa_id,
        Microciclo.data_inicio == data_inicio,
        Microciclo.data_fim == data_fim,
    ).order_by(Microciclo.data_inicio.desc(), Microciclo.id.desc()).first()


def _obter_microciclo_que_cobre_intervalo(
    db: Session,
    equipa_id: int,
    data_inicio: date,
    data_fim: date,
) -> Microciclo | None:
    """Procura um microciclo da equipa que já cubra todo o intervalo semanal."""
    return db.query(Microciclo).join(Mesociclo).join(Macrociclo).filter(
        Macrociclo.equipa_id == equipa_id,
        Microciclo.data_inicio <= data_inicio,
        Microciclo.data_fim >= data_fim,
    ).order_by(Microciclo.data_inicio.desc(), Microciclo.id.desc()).first()


def _obter_ou_criar_macrociclo_para_equipa_intervalo(
    db: Session,
    equipa_id: int,
    data_inicio: date,
    data_fim: date,
) -> Macrociclo:
    """Obtém um macrociclo da equipa que cobre o intervalo ou cria um novo."""
    planeamento_anual = db.query(PlaneamentoAnualEquipa).filter(
        PlaneamentoAnualEquipa.equipa_id == equipa_id,
        PlaneamentoAnualEquipa.data_inicio <= data_inicio,
        PlaneamentoAnualEquipa.data_fim >= data_fim,
    ).order_by(PlaneamentoAnualEquipa.data_inicio.desc()).first()
    if not planeamento_anual:
        equipa = db.query(Equipa).filter(Equipa.id == equipa_id).first()
        anual_clube = db.query(PlaneamentoClubeAnual).filter(
            PlaneamentoClubeAnual.data_inicio <= data_inicio,
            PlaneamentoClubeAnual.data_fim >= data_fim,
        ).order_by(PlaneamentoClubeAnual.data_inicio.desc()).first()
        if anual_clube:
            inicio_anual, fim_anual = anual_clube.data_inicio, anual_clube.data_fim
            epoca = anual_clube.epoca
        else:
            ano = data_inicio.year if data_inicio.month >= 7 else data_inicio.year - 1
            inicio_anual, fim_anual = date(ano, 7, 1), date(ano + 1, 6, 30)
            epoca = f"{ano}/{ano + 1}"
        planeamento_anual = PlaneamentoAnualEquipa(
            clube_id=equipa.clube_id,
            equipa_id=equipa_id,
            planeamento_clube_anual_id=anual_clube.id if anual_clube else None,
            epoca=epoca,
            titulo=f"Planeamento anual {epoca}",
            data_inicio=inicio_anual,
            data_fim=fim_anual,
            objetivos_gerais=anual_clube.objetivos_gerais if anual_clube else None,
        )
        db.add(planeamento_anual)
        db.flush()

    macrociclo = db.query(Macrociclo).filter(
        Macrociclo.planeamento_anual_equipa_id == planeamento_anual.id,
        Macrociclo.data_inicio <= data_inicio,
        Macrociclo.data_fim >= data_fim,
    ).order_by(Macrociclo.data_inicio.desc(), Macrociclo.id.desc()).first()
    if macrociclo:
        return macrociclo

    total_macrociclos = db.query(Macrociclo).filter(
        Macrociclo.planeamento_anual_equipa_id == planeamento_anual.id,
    ).count()
    macrociclo = Macrociclo(
        numero=total_macrociclos + 1,
        data_inicio=planeamento_anual.data_inicio,
        data_fim=planeamento_anual.data_fim,
        equipa_id=equipa_id,
        planeamento_anual_equipa_id=planeamento_anual.id,
        reflexao="Macrociclo criado automaticamente para suportar sessões do planeamento global.",
    )
    db.add(macrociclo)
    db.flush()
    renumerar_macrociclos(db, equipa_id, planeamento_anual.id)
    return macrociclo


def _obter_ou_criar_mesociclo_para_intervalo(
    db: Session,
    macrociclo: Macrociclo,
    data_inicio: date,
    data_fim: date,
) -> Mesociclo:
    """Obtém um mesociclo que cobre o intervalo ou cria um novo com o mesmo período semanal."""
    mesociclo = db.query(Mesociclo).filter(
        Mesociclo.macrociclo_id == macrociclo.id,
        Mesociclo.data_inicio <= data_inicio,
        Mesociclo.data_fim >= data_fim,
    ).order_by(Mesociclo.data_inicio.desc(), Mesociclo.id.desc()).first()
    if mesociclo:
        return mesociclo

    total_mesociclos = db.query(Mesociclo).filter(Mesociclo.macrociclo_id == macrociclo.id).count()
    mesociclo = Mesociclo(
        numero=total_mesociclos + 1,
        data_inicio=data_inicio,
        data_fim=data_fim,
        macrociclo_id=macrociclo.id,
        reflexao="Mesociclo criado automaticamente para suportar sessões do planeamento global.",
    )
    db.add(mesociclo)
    db.flush()
    renumerar_mesociclos(db, macrociclo.id)
    return mesociclo


def _criar_microciclo_automatico(
    db: Session,
    mesociclo: Mesociclo,
    data_inicio: date,
    data_fim: date,
) -> Microciclo:
    """Cria um microciclo semanal automático dentro do mesociclo indicado."""
    total_microciclos = db.query(Microciclo).filter(Microciclo.mesociclo_id == mesociclo.id).count()
    microciclo = Microciclo(
        numero=total_microciclos + 1,
        data_inicio=data_inicio,
        data_fim=data_fim,
        tipo="automatico_planeamento_global",
        reflexao="Microciclo criado automaticamente para integrar sessões do planeamento global.",
        mesociclo_id=mesociclo.id,
    )
    db.add(microciclo)
    db.flush()
    renumerar_microciclos(db, mesociclo.id)
    return microciclo


def _obter_ou_criar_microciclo_para_equipa_e_data(db: Session, equipa_id: int, data_evento: date) -> Microciclo:
    """Obtém o microciclo da semana ou cria automaticamente a estrutura mínima em falta."""
    data_inicio, data_fim = _obter_intervalo_semana(data_evento)

    microciclo = _obter_microciclo_existente_equipa_semana(db, equipa_id, data_inicio, data_fim)
    if microciclo:
        return microciclo

    microciclo = _obter_microciclo_que_cobre_intervalo(db, equipa_id, data_inicio, data_fim)
    if microciclo:
        return microciclo

    macrociclo = _obter_ou_criar_macrociclo_para_equipa_intervalo(db, equipa_id, data_inicio, data_fim)
    mesociclo = _obter_ou_criar_mesociclo_para_intervalo(db, macrociclo, data_inicio, data_fim)

    microciclo = _obter_microciclo_existente_equipa_semana(db, equipa_id, data_inicio, data_fim)
    if microciclo:
        return microciclo

    return _criar_microciclo_automatico(db, mesociclo, data_inicio, data_fim)


def _combinar_local_evento(evento: EventoPlaneamentoClube) -> str | None:
    """Resolve um texto de local simples para a sessão gerada."""
    if evento.espaco and evento.espaco.nome:
        return evento.espaco.nome
    if evento.jogo and evento.jogo.local:
        return evento.jogo.local
    if evento.atividade and evento.atividade.local:
        return evento.atividade.local
    return None


def _combinar_horario_evento(evento: EventoPlaneamentoClube) -> tuple[str | None, str | None]:
    """Resolve o intervalo horário mais útil para a sessão gerada."""
    hora_inicio = normalizar_hora(
        evento.hora_inicio or (evento.jogo.hora if evento.jogo and evento.jogo.hora else None)
    )
    hora_fim = normalizar_hora(evento.hora_fim)
    return hora_inicio, hora_fim


def _combinar_reflexao_evento(evento: EventoPlaneamentoClube) -> str | None:
    """Agrupa observações operacionais relevantes do evento num campo simples."""
    partes = []
    if evento.titulo:
        partes.append(f"Evento global: {evento.titulo}")
    if evento.descricao:
        partes.append(evento.descricao)
    if evento.observacoes:
        partes.append(evento.observacoes)
    return "\n".join(partes) if partes else None


def _obter_sessao_existente_evento(
    db: Session,
    evento_id: int,
    equipa_id: int,
) -> SessaoTreino | None:
    """Procura uma sessão já gerada para o mesmo evento e equipa."""
    return db.query(SessaoTreino).join(Microciclo).join(Mesociclo).join(Macrociclo).filter(
        SessaoTreino.origem == "planeamento_global",
        SessaoTreino.evento_planeamento_clube_id == evento_id,
        Macrociclo.equipa_id == equipa_id,
    ).first()


def _obter_sessoes_sincronizadas_semanal(db: Session, semanal_id: int) -> list[SessaoTreino]:
    """Lista as sessões geradas a partir de um plano semanal específico."""
    return db.query(SessaoTreino).filter(
        SessaoTreino.plano_semanal_clube_id == semanal_id,
        SessaoTreino.origem == "planeamento_global",
    ).all()


def _obter_equipa_id_por_sessao(sessao: SessaoTreino) -> int | None:
    """Resolve a equipa da sessão pela hierarquia de planeamento."""
    if not sessao.microciclo or not sessao.microciclo.mesociclo or not sessao.microciclo.mesociclo.macrociclo:
        return None
    return sessao.microciclo.mesociclo.macrociclo.equipa_id


def _calcular_numero_treino_microciclo(
    db: Session,
    microciclo_id: int,
    sessao_id_excluir: int | None = None,
    tipo_treino: str = "normal",
) -> int:
    """Calcula o próximo número, separado entre treino normal e físico."""
    query = db.query(SessaoTreino).filter(
        SessaoTreino.microciclo_id == microciclo_id,
        SessaoTreino.e_jogo == False,
        SessaoTreino.ativa == True,
        SessaoTreino.tipo_treino == tipo_treino,
    )
    if sessao_id_excluir:
        query = query.filter(SessaoTreino.id != sessao_id_excluir)
    total_treinos = query.count()
    return total_treinos + 1


def _criar_ou_atualizar_sessao_evento(
    db: Session,
    semanal: PlanoSemanalClube,
    evento: EventoPlaneamentoClube,
    equipa: Equipa,
) -> str:
    """Cria ou actualiza uma sessão operacional gerada pelo planeamento global."""
    sessao_existente = _obter_sessao_existente_evento(db, evento.id, equipa.id)
    microciclo = _obter_ou_criar_microciclo_para_equipa_e_data(db, equipa.id, evento.data)

    local = _combinar_local_evento(evento)
    hora_inicio, hora_fim = _combinar_horario_evento(evento)
    reflexao = _combinar_reflexao_evento(evento)
    tipo_treino = "fisico" if evento.tipo == TipoEventoPlaneamentoClubeEnum.treino_fisico else "normal"

    if sessao_existente:
        if sessao_existente.alterada_manual:
            sessao_existente.ativa = True
            sessao_existente.sincronizada = False
            return "ignorada_manual"

        mudou_microciclo = sessao_existente.microciclo_id != microciclo.id
        sessao_existente.data = evento.data
        sessao_existente.local = local
        sessao_existente.hora_inicio = hora_inicio
        sessao_existente.hora_fim = hora_fim
        sessao_existente.e_jogo = False
        sessao_existente.tipo_treino = tipo_treino
        sessao_existente.microciclo_id = microciclo.id
        sessao_existente.origem = "planeamento_global"
        sessao_existente.plano_semanal_clube_id = semanal.id
        sessao_existente.evento_planeamento_clube_id = evento.id
        sessao_existente.reflexao = reflexao
        sessao_existente.ativa = True
        sessao_existente.sincronizada = True
        if mudou_microciclo or sessao_existente.numero_treino is None:
            sessao_existente.numero_treino = _calcular_numero_treino_microciclo(
                db,
                microciclo.id,
                sessao_id_excluir=sessao_existente.id,
                tipo_treino=tipo_treino,
            )
        renumerar_treinos_equipa(db, equipa.id)
        return "atualizada"

    sessao = SessaoTreino(
        data=evento.data,
        local=local,
        hora_inicio=hora_inicio,
        hora_fim=hora_fim,
        numero_treino=_calcular_numero_treino_microciclo(db, microciclo.id, tipo_treino=tipo_treino),
        tipo_treino=tipo_treino,
        volume_minutos=None,
        intensidade_rpe=None,
        e_jogo=False,
        reflexao=reflexao,
        origem="planeamento_global",
        sincronizada=True,
        alterada_manual=False,
        ativa=True,
        microciclo_id=microciclo.id,
        plano_semanal_clube_id=semanal.id,
        evento_planeamento_clube_id=evento.id,
    )
    db.add(sessao)
    db.flush()
    renumerar_treinos_equipa(db, equipa.id)
    return "criada"


def _desativar_sessoes_orfas_ou_fora_de_escopo(
    db: Session,
    semanal_id: int,
    pares_evento_equipa_ativos: set[tuple[int, int]],
) -> int:
    """Desactiva sessões cujo evento desapareceu ou deixou de se aplicar à equipa."""
    total_inativadas = 0
    for sessao in _obter_sessoes_sincronizadas_semanal(db, semanal_id):
        equipa_id = _obter_equipa_id_por_sessao(sessao)
        if not sessao.evento_planeamento_clube_id or not equipa_id:
            continue
        if (sessao.evento_planeamento_clube_id, equipa_id) not in pares_evento_equipa_ativos:
            sessao.ativa = False
            sessao.sincronizada = False
            total_inativadas += 1
    return total_inativadas


def _sincronizar_plano_semanal(db: Session, semanal: PlanoSemanalClube) -> dict[str, int]:
    """Sincroniza o plano semanal com as sessões operacionais das equipas."""
    resumo = {
        "eventos_operacionais": 0,
        "geradas": 0,
        "atualizadas": 0,
        "ignoradas": 0,
        "ignoradas_manuais": 0,
        "sem_microciclo": 0,
        "inativadas": 0,
    }

    eventos = db.query(EventoPlaneamentoClube).filter(
        EventoPlaneamentoClube.plano_semanal_id == semanal.id
    ).order_by(EventoPlaneamentoClube.data.asc(), EventoPlaneamentoClube.hora_inicio.asc()).all()
    pares_evento_equipa_ativos: set[tuple[int, int]] = set()

    for evento in eventos:
        if not _tipo_evento_gera_sessao(evento):
            resumo["ignoradas"] += 1
            continue

        resumo["eventos_operacionais"] += 1
        equipas_alvo = _obter_equipas_alvo_evento(db, evento)
        if not equipas_alvo:
            resumo["ignoradas"] += 1
            continue

        for equipa in equipas_alvo:
            pares_evento_equipa_ativos.add((evento.id, equipa.id))
            resultado = _criar_ou_atualizar_sessao_evento(db, semanal, evento, equipa)
            if resultado == "criada":
                resumo["geradas"] += 1
            elif resultado == "atualizada":
                resumo["atualizadas"] += 1
            elif resultado == "ignorada_manual":
                resumo["ignoradas_manuais"] += 1
            elif resultado == "sem_microciclo":
                resumo["sem_microciclo"] += 1

    resumo["inativadas"] = _desativar_sessoes_orfas_ou_fora_de_escopo(db, semanal.id, pares_evento_equipa_ativos)
    return resumo


def _construir_calendario_mensal(mensal: PlaneamentoClubeMensal, eventos: list[EventoPlaneamentoClube]):
    """Monta uma grelha mensal simples com eventos agrupados por dia."""
    eventos_por_data = {}
    for evento in eventos:
        eventos_por_data.setdefault(evento.data, []).append(evento)

    for lista_eventos in eventos_por_data.values():
        lista_eventos.sort(key=lambda item: (item.hora_inicio or "", item.titulo))

    semanas = []
    for semana in calendar.Calendar(firstweekday=0).monthdatescalendar(mensal.ano, mensal.mes):
        semanas.append([
            {
                "data": dia,
                "dia": dia.day,
                "do_mes_atual": dia.month == mensal.mes,
                "eventos": eventos_por_data.get(dia, []),
            }
            for dia in semana
        ])

    return {
        "ano": mensal.ano,
        "mes": mensal.mes,
        "nome_mes": calendar.month_name[mensal.mes],
        "dias_semana": ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"],
        "semanas": semanas,
    }


def _construir_calendario_anual_quadros(
    planeamento: PlaneamentoClubeAnual,
    eventos: list[EventoPlaneamentoClube],
):
    """Monta os meses do período anual como grelhas de calendário estáveis."""
    eventos_por_data = {}
    for evento in eventos:
        eventos_por_data.setdefault(evento.data, []).append(evento)

    for lista_eventos in eventos_por_data.values():
        lista_eventos.sort(key=lambda item: (item.hora_inicio or "", item.titulo))

    meses = []
    cursor = date(planeamento.data_inicio.year, planeamento.data_inicio.month, 1)
    limite = date(planeamento.data_fim.year, planeamento.data_fim.month, 1)

    while cursor <= limite:
        semanas = []
        for semana in calendar.Calendar(firstweekday=0).monthdatescalendar(cursor.year, cursor.month):
            semanas.append([
                {
                    "data": dia,
                    "dia": dia.day,
                    "do_mes_atual": dia.month == cursor.month,
                    "fim_semana": dia.weekday() >= 5,
                    "eventos": eventos_por_data.get(dia, []),
                }
                for dia in semana
            ])
        meses.append({
            "ano": cursor.year,
            "mes": cursor.month,
            "nome_mes": calendar.month_name[cursor.month],
            "semanas": semanas,
        })

        if cursor.month == 12:
            cursor = date(cursor.year + 1, 1, 1)
        else:
            cursor = date(cursor.year, cursor.month + 1, 1)

    return {"meses": meses, "dias_semana": ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]}


def _construir_calendario_semanal(semanal: PlanoSemanalClube, eventos: list[EventoPlaneamentoClube], atribuicoes: list[AtribuicaoEspacoSemanal]):
    """Monta a estrutura semanal com eventos e atribuições agrupados por dia."""
    eventos_por_data = {}
    for evento in eventos:
        eventos_por_data.setdefault(evento.data, []).append(evento)

    atribuicoes_por_data = {}
    for atribuicao in atribuicoes:
        atribuicoes_por_data.setdefault(atribuicao.data, []).append(atribuicao)

    dias = []
    nomes_semana = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
    for indice in range(7):
        data_dia = semanal.data_inicio + timedelta(days=indice)
        eventos_dia = sorted(
            eventos_por_data.get(data_dia, []),
            key=lambda item: (item.hora_inicio or "", item.titulo),
        )
        atribuicoes_dia = sorted(
            atribuicoes_por_data.get(data_dia, []),
            key=lambda item: (item.hora_inicio, item.espaco.nome if item.espaco else ""),
        )
        itens_dia = []
        for evento in eventos_dia:
                itens_dia.append({
                    "tipo": "evento",
                    "titulo": evento.titulo,
                    "detalhe": _formatar_intervalo_calendario(evento.hora_inicio, evento.hora_fim),
                    "subtitulo": evento.tipo.value,
                    "link": f"/planeamento-clube/eventos/{evento.id}",
                    "pill": "Evento",
                    "classes": "border-amber-100 bg-amber-50",
                    "ordem": evento.hora_inicio or "99:99",
            })
        for atribuicao in atribuicoes_dia:
                itens_dia.append({
                    "tipo": "atribuicao",
                    "titulo": atribuicao.espaco.nome if atribuicao.espaco else "Espaço por definir",
                    "detalhe": _formatar_intervalo_calendario(atribuicao.hora_inicio, atribuicao.hora_fim),
                    "subtitulo": atribuicao.equipa.nome if atribuicao.equipa else atribuicao.tipo_ocupacao.value,
                    "link": f"/planeamento-clube/atribuicoes/{atribuicao.id}",
                    "pill": "Espaço",
                    "classes": "border-sky-100 bg-sky-50",
                "ordem": atribuicao.hora_inicio or "99:99",
            })
        itens_dia.sort(key=lambda item: (item["ordem"], item["titulo"]))
        dias.append({
            "data": data_dia,
            "nome_semana": nomes_semana[data_dia.weekday()],
            "eventos": eventos_dia,
            "atribuicoes": atribuicoes_dia,
            "itens": itens_dia,
        })

    return {"dias": dias}


def _obter_mensagem_erro_eliminacao(codigo: str | None):
    """Traduz um código de erro de eliminação numa mensagem legível."""
    return MENSAGENS_ERRO_ELIMINACAO.get(codigo)


@router.get("/vista", response_class=HTMLResponse)
def vista_treinador(request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_coordenacao)):
    hoje = date.today()
    fim_janela = hoje + timedelta(days=30)

    mensal_atual = (
        db.query(PlaneamentoClubeMensal)
        .filter(PlaneamentoClubeMensal.ano == hoje.year, PlaneamentoClubeMensal.mes == hoje.month)
        .first()
    )

    planos_semanais = (
        db.query(PlanoSemanalClube)
        .filter(PlanoSemanalClube.data_fim >= hoje, PlanoSemanalClube.data_inicio <= fim_janela)
        .order_by(PlanoSemanalClube.data_inicio)
        .limit(6)
        .all()
    )

    eventos_proximos = (
        db.query(EventoPlaneamentoClube)
        .filter(EventoPlaneamentoClube.data >= hoje, EventoPlaneamentoClube.data <= fim_janela)
        .order_by(EventoPlaneamentoClube.data, EventoPlaneamentoClube.hora_inicio)
        .all()
    )

    anual_ativo = (
        db.query(PlaneamentoClubeAnual)
        .filter(PlaneamentoClubeAnual.ativo == True)
        .order_by(PlaneamentoClubeAnual.data_inicio.desc())
        .first()
    )

    return templates.TemplateResponse(request, "planeamento_clube/vista_treinador.html", {
        "utilizador": utilizador,
        "hoje": hoje,
        "mensal_atual": mensal_atual,
        "planos_semanais": planos_semanais,
        "eventos_proximos": eventos_proximos,
        "anual_ativo": anual_ativo,
    })


@router.get("/anual", response_class=HTMLResponse)
def listar_planeamentos_anuais(request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_coordenacao)):

    planeamentos = db.query(PlaneamentoClubeAnual).order_by(PlaneamentoClubeAnual.data_inicio.desc()).all()
    return templates.TemplateResponse(request, "planeamento_clube/anual_lista.html", {
        "utilizador": utilizador,
        "planeamentos": planeamentos,
        "erro": _obter_mensagem_erro_eliminacao(request.query_params.get("erro")),
    })


@router.get("/mensal", response_class=HTMLResponse)
def listar_planeamentos_mensais(request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_coordenacao)):

    ano = request.query_params.get("ano", "").strip()
    mes = request.query_params.get("mes", "").strip()
    planeamento_anual_id = request.query_params.get("planeamento_anual_id", "").strip()

    query = db.query(PlaneamentoClubeMensal).order_by(
        PlaneamentoClubeMensal.ano.desc(),
        PlaneamentoClubeMensal.mes.desc(),
    )

    if ano.isdigit():
        query = query.filter(PlaneamentoClubeMensal.ano == int(ano))
    if mes.isdigit():
        query = query.filter(PlaneamentoClubeMensal.mes == int(mes))
    if planeamento_anual_id.isdigit():
        query = query.filter(PlaneamentoClubeMensal.planeamento_anual_id == int(planeamento_anual_id))

    mensais = query.all()

    return templates.TemplateResponse(request, "planeamento_clube/mensal_lista.html", {
        "utilizador": utilizador,
        "mensais": mensais,
        "planeamentos_anuais": db.query(PlaneamentoClubeAnual).order_by(PlaneamentoClubeAnual.data_inicio.desc()).all(),
        "filtros_aplicados": {
            "ano": ano,
            "mes": mes,
            "planeamento_anual_id": planeamento_anual_id,
        },
    })


@router.get("/semanal", response_class=HTMLResponse)
def listar_planos_semanais(request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_secretaria)):

    planeamento_mensal_id = request.query_params.get("planeamento_mensal_id", "").strip()
    estado = request.query_params.get("estado", "").strip()

    query = db.query(PlanoSemanalClube).order_by(PlanoSemanalClube.data_inicio.desc())

    if planeamento_mensal_id.isdigit():
        query = query.filter(PlanoSemanalClube.planeamento_mensal_id == int(planeamento_mensal_id))
    if estado:
        query = query.filter(PlanoSemanalClube.estado == estado)

    semanais = query.all()

    return templates.TemplateResponse(request, "planeamento_clube/semanal_lista.html", {
        "utilizador": utilizador,
        "semanais": semanais,
        "planeamentos_mensais": db.query(PlaneamentoClubeMensal).order_by(
            PlaneamentoClubeMensal.ano.desc(),
            PlaneamentoClubeMensal.mes.desc(),
        ).all(),
        "filtros_aplicados": {
            "planeamento_mensal_id": planeamento_mensal_id,
            "estado": estado,
        },
        "estados_semanal": _obter_contexto_form_semanal()["estados_semanal"],
        "pode_gerir": verificar_perfil(utilizador, ["administrador", "coordenador", "superadministrador"]),
    })


@router.get("/anual/novo", response_class=HTMLResponse)
def form_novo_planeamento_anual(request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_coordenacao)):

    contexto = _obter_contexto_form_anual()
    contexto.update({
        "utilizador": utilizador,
        "planeamento": None,
        "modo": "criar",
    })
    return templates.TemplateResponse(request, "planeamento_clube/anual_form.html", contexto)


@router.post("/anual/novo")
async def criar_planeamento_anual(
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_coordenacao),
    epoca: str = Form(...),
    titulo: str = Form(...),
    data_inicio: str = Form(...),
    data_fim: str = Form(...),
    objetivos_gerais: str = Form(""),
    observacoes: str = Form(""),
    ativo: str = Form("true"),
):

    try:
        planeamento = _criar_planeamento_anual(
            epoca,
            titulo,
            data_inicio,
            data_fim,
            objetivos_gerais,
            observacoes,
            ativo,
        )
    except ValueError as erro:
        set_flash(request, str(erro), "error")
        return RedirectResponse(url="/planeamento-clube/anual/novo", status_code=303)
    db.add(planeamento)
    db.flush()
    registar_historico_planeamento(db, utilizador, "planeamento_anual", planeamento.id, "criado", planeamento.titulo)
    registar_auditoria(db, utilizador, "criar", "planeamento_anual", planeamento.id, planeamento.titulo, request)
    db.commit()
    db.refresh(planeamento)

    return RedirectResponse(url=f"/planeamento-clube/anual/{planeamento.id}", status_code=303)


@router.get("/anual/{anual_id}", response_class=HTMLResponse)
def detalhe_planeamento_anual(anual_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_coordenacao)):

    planeamento = db.query(PlaneamentoClubeAnual).filter(PlaneamentoClubeAnual.id == anual_id).first()
    if not planeamento:
        return RedirectResponse(url="/planeamento-clube/anual")

    mensais = db.query(PlaneamentoClubeMensal).filter(
        PlaneamentoClubeMensal.planeamento_anual_id == anual_id
    ).order_by(PlaneamentoClubeMensal.ano, PlaneamentoClubeMensal.mes).all()
    eventos = db.query(EventoPlaneamentoClube).filter(
        EventoPlaneamentoClube.planeamento_anual_id == anual_id
    ).order_by(EventoPlaneamentoClube.data.desc(), EventoPlaneamentoClube.hora_inicio.desc()).all()
    dashboard_planeamento = obter_dashboard_planeamento_anual(
        db,
        planeamento.data_inicio,
        planeamento.data_fim,
    )
    historico = db.query(HistoricoPlaneamentoClube).filter(
        HistoricoPlaneamentoClube.entidade == "planeamento_anual",
        HistoricoPlaneamentoClube.entidade_id == anual_id,
    ).order_by(HistoricoPlaneamentoClube.criado_em.desc()).limit(20).all()
    planeamentos_equipas = db.query(PlaneamentoAnualEquipa).filter(
        PlaneamentoAnualEquipa.planeamento_clube_anual_id == anual_id,
    ).order_by(PlaneamentoAnualEquipa.epoca, PlaneamentoAnualEquipa.equipa_id).all()

    return templates.TemplateResponse(request, "planeamento_clube/anual_detalhe.html", {
        "utilizador": utilizador,
        "planeamento": planeamento,
        "mensais": mensais,
        "eventos": eventos,
        "dashboard_planeamento": dashboard_planeamento,
        "historico": historico,
        "planeamentos_equipas": planeamentos_equipas,
        "erro": _obter_mensagem_erro_eliminacao(request.query_params.get("erro")),
    })


@router.get("/mensal/novo", response_class=HTMLResponse)
def form_novo_planeamento_mensal(request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_coordenacao)):
    anuais = db.query(PlaneamentoClubeAnual).order_by(PlaneamentoClubeAnual.data_inicio.desc()).all()
    return templates.TemplateResponse(request, "planeamento_clube/mensal_form.html", {
        "utilizador": utilizador, "mensal": None, "planeamentos_anuais": anuais, "modo": "criar",
        **_obter_contexto_form_mensal(),
    })


@router.post("/mensal/novo")
async def criar_planeamento_mensal_direto(
    request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_coordenacao),
    planeamento_anual_id: str = Form(...), ano: str = Form(...), mes: str = Form(...), titulo: str = Form(...),
    objetivos_mes: str = Form(""), observacoes: str = Form(""), estado: str = Form("rascunho"),
):
    try:
        anual_id = _converter_id(planeamento_anual_id, "Planeamento anual", obrigatorio=True)
        if not db.query(PlaneamentoClubeAnual).filter(PlaneamentoClubeAnual.id == anual_id).first():
            raise ValueError("Seleciona um planeamento anual válido.")
        mensal = _criar_planeamento_mensal(anual_id, ano, mes, titulo, objetivos_mes, observacoes, estado)
    except ValueError as erro:
        set_flash(request, str(erro), "error")
        return RedirectResponse(url="/planeamento-clube/mensal/novo", status_code=303)
    db.add(mensal)
    db.flush()
    registar_historico_planeamento(db, utilizador, "planeamento_mensal", mensal.id, "criado", mensal.titulo)
    registar_auditoria(db, utilizador, "criar", "planeamento_mensal", mensal.id, mensal.titulo, request)
    db.commit()
    return RedirectResponse(url=f"/planeamento-clube/mensal/{mensal.id}", status_code=303)


@router.get("/anual/{anual_id}/pdf")
def exportar_pdf_planeamento_anual(
    anual_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_coordenacao),
):
    planeamento = db.query(PlaneamentoClubeAnual).filter(PlaneamentoClubeAnual.id == anual_id).first()
    if not planeamento:
        return RedirectResponse(url="/planeamento-clube/anual")
    mensais = db.query(PlaneamentoClubeMensal).filter(
        PlaneamentoClubeMensal.planeamento_anual_id == anual_id
    ).order_by(PlaneamentoClubeMensal.ano, PlaneamentoClubeMensal.mes).all()
    eventos = db.query(EventoPlaneamentoClube).filter(
        EventoPlaneamentoClube.data >= planeamento.data_inicio,
        EventoPlaneamentoClube.data <= planeamento.data_fim,
    ).order_by(EventoPlaneamentoClube.data.asc(), EventoPlaneamentoClube.hora_inicio.asc()).all()
    dashboard_planeamento = obter_dashboard_planeamento_anual(db, planeamento.data_inicio, planeamento.data_fim)
    return _responder_pdf(
        request,
        "planeamento_clube/anual_pdf.html",
        {
            "utilizador": utilizador,
            "planeamento": planeamento,
            "mensais": mensais,
            "eventos": eventos,
            "dashboard_planeamento": dashboard_planeamento,
            "hoje": date.today(),
        },
        f"planeamento_anual_{planeamento.epoca}_{planeamento.id}.pdf",
    )


@router.get("/anual/{anual_id}/calendario", response_class=HTMLResponse)
def calendario_planeamento_anual(anual_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_coordenacao)):

    planeamento = db.query(PlaneamentoClubeAnual).filter(PlaneamentoClubeAnual.id == anual_id).first()
    if not planeamento:
        return RedirectResponse(url="/planeamento-clube/anual")

    eventos = db.query(EventoPlaneamentoClube).filter(
        EventoPlaneamentoClube.data >= planeamento.data_inicio,
        EventoPlaneamentoClube.data <= planeamento.data_fim,
    ).order_by(EventoPlaneamentoClube.data.asc(), EventoPlaneamentoClube.hora_inicio.asc()).all()
    calendario_anual = _construir_calendario_anual_quadros(planeamento, eventos)

    return templates.TemplateResponse(request, "planeamento_clube/anual_calendario.html", {
        "utilizador": utilizador,
        "planeamento": planeamento,
        "eventos": eventos,
        "calendario_anual": calendario_anual,
        "metadados_tipo_agenda": metadados_tipo_agenda,
        "agenda_tipos": tipos_agenda_formulario(),
    })


@router.get("/anual/{anual_id}/calendario/pdf")
def exportar_pdf_calendario_anual(
    anual_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_coordenacao),
):
    planeamento = db.query(PlaneamentoClubeAnual).filter(PlaneamentoClubeAnual.id == anual_id).first()
    if not planeamento:
        return RedirectResponse(url="/planeamento-clube/anual")
    eventos = db.query(EventoPlaneamentoClube).filter(
        EventoPlaneamentoClube.data >= planeamento.data_inicio,
        EventoPlaneamentoClube.data <= planeamento.data_fim,
    ).order_by(EventoPlaneamentoClube.data.asc(), EventoPlaneamentoClube.hora_inicio.asc()).all()
    calendario_anual = _construir_calendario_anual_quadros(planeamento, eventos)
    return _responder_pdf(
        request,
        "planeamento_clube/anual_calendario_pdf.html",
        {"utilizador": utilizador, "planeamento": planeamento, "eventos": eventos, "calendario_anual": calendario_anual, "hoje": date.today()},
        f"calendario_anual_{planeamento.epoca}_{planeamento.id}.pdf",
    )


@router.get("/anual/{anual_id}/editar", response_class=HTMLResponse)
def form_editar_planeamento_anual(anual_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_coordenacao)):

    planeamento = db.query(PlaneamentoClubeAnual).filter(PlaneamentoClubeAnual.id == anual_id).first()
    if not planeamento:
        return RedirectResponse(url="/planeamento-clube/anual")

    contexto = _obter_contexto_form_anual()
    contexto.update({
        "utilizador": utilizador,
        "planeamento": planeamento,
        "modo": "editar",
    })
    return templates.TemplateResponse(request, "planeamento_clube/anual_form.html", contexto)


@router.post("/anual/{anual_id}/editar")
async def editar_planeamento_anual(
    anual_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_coordenacao),
    epoca: str = Form(...),
    titulo: str = Form(...),
    data_inicio: str = Form(...),
    data_fim: str = Form(...),
    objetivos_gerais: str = Form(""),
    observacoes: str = Form(""),
    ativo: str = Form("true"),
):

    planeamento = db.query(PlaneamentoClubeAnual).filter(PlaneamentoClubeAnual.id == anual_id).first()
    if not planeamento:
        return RedirectResponse(url="/planeamento-clube/anual")

    try:
        _atualizar_planeamento_anual(
            planeamento,
            epoca,
            titulo,
            data_inicio,
            data_fim,
            objetivos_gerais,
            observacoes,
            ativo,
        )
    except ValueError as erro:
        set_flash(request, str(erro), "error")
        return RedirectResponse(url=f"/planeamento-clube/anual/{planeamento.id}/editar", status_code=303)
    registar_historico_planeamento(db, utilizador, "planeamento_anual", planeamento.id, "editado", planeamento.titulo)
    registar_auditoria(db, utilizador, "editar", "planeamento_anual", planeamento.id, planeamento.titulo, request)
    db.commit()

    return RedirectResponse(url=f"/planeamento-clube/anual/{planeamento.id}", status_code=303)


@router.post("/anual/{anual_id}/eliminar")
async def eliminar_planeamento_anual(anual_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_coordenacao)):

    planeamento = db.query(PlaneamentoClubeAnual).filter(PlaneamentoClubeAnual.id == anual_id).first()
    if not planeamento:
        return RedirectResponse(url="/planeamento-clube/anual", status_code=303)

    registar_auditoria(db, utilizador, "apagar", "planeamento_anual", planeamento.id, planeamento.titulo, request)
    db.delete(planeamento)
    db.commit()

    return RedirectResponse(url="/planeamento-clube/anual", status_code=303)


@router.post("/anual/{anual_id}/mensal/novo")
async def criar_planeamento_mensal(
    anual_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_coordenacao),
    ano: str = Form(...),
    mes: str = Form(...),
    titulo: str = Form(...),
    objetivos_mes: str = Form(""),
    observacoes: str = Form(""),
    estado: str = Form("rascunho"),
):

    planeamento_anual = db.query(PlaneamentoClubeAnual).filter(PlaneamentoClubeAnual.id == anual_id).first()
    if not planeamento_anual:
        return RedirectResponse(url="/planeamento-clube/anual")

    try:
        mensal = _criar_planeamento_mensal(
            anual_id,
            ano,
            mes,
            titulo,
            objetivos_mes,
            observacoes,
            estado,
        )
    except ValueError as erro:
        set_flash(request, str(erro), "error")
        return RedirectResponse(url=f"/planeamento-clube/anual/{anual_id}", status_code=303)
    db.add(mensal)
    db.flush()
    registar_historico_planeamento(db, utilizador, "planeamento_mensal", mensal.id, "criado", mensal.titulo)
    registar_auditoria(db, utilizador, "criar", "planeamento_mensal", mensal.id, mensal.titulo, request)
    db.commit()
    db.refresh(mensal)

    return RedirectResponse(url=f"/planeamento-clube/mensal/{mensal.id}", status_code=303)


@router.get("/mensal/{mensal_id}", response_class=HTMLResponse)
def detalhe_planeamento_mensal(mensal_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_coordenacao)):

    mensal = db.query(PlaneamentoClubeMensal).filter(PlaneamentoClubeMensal.id == mensal_id).first()
    if not mensal:
        return RedirectResponse(url="/planeamento-clube/anual")

    semanais = db.query(PlanoSemanalClube).filter(
        PlanoSemanalClube.planeamento_mensal_id == mensal_id
    ).order_by(PlanoSemanalClube.data_inicio).all()
    resumo_operacional = obter_resumo_operacional_mensal(db, mensal)
    eventos = list(reversed(resumo_operacional["eventos"]))
    calendario_mensal = _construir_calendario_mensal(mensal, resumo_operacional["eventos"])

    historico = db.query(HistoricoPlaneamentoClube).filter(
        HistoricoPlaneamentoClube.entidade == "planeamento_mensal",
        HistoricoPlaneamentoClube.entidade_id == mensal_id,
    ).order_by(HistoricoPlaneamentoClube.criado_em.desc()).limit(20).all()

    return templates.TemplateResponse(request, "planeamento_clube/mensal_detalhe.html", {
        "utilizador": utilizador,
        "mensal": mensal,
        "semanais": semanais,
        "eventos": eventos,
        "calendario_mensal": calendario_mensal,
        "resumo_operacional_equipas": resumo_operacional["resumo_equipas"],
        "jogos_do_mes": resumo_operacional["jogos_mes"],
        "estatisticas_operacionais": resumo_operacional["estatisticas"],
        "historico": historico,
        "erro": _obter_mensagem_erro_eliminacao(request.query_params.get("erro")),
    })


@router.get("/mensal/{mensal_id}/pdf")
def exportar_pdf_planeamento_mensal(
    mensal_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_coordenacao),
):
    mensal = db.query(PlaneamentoClubeMensal).filter(PlaneamentoClubeMensal.id == mensal_id).first()
    if not mensal:
        return RedirectResponse(url="/planeamento-clube/anual")
    semanais = db.query(PlanoSemanalClube).filter(
        PlanoSemanalClube.planeamento_mensal_id == mensal_id
    ).order_by(PlanoSemanalClube.data_inicio).all()
    resumo_operacional = obter_resumo_operacional_mensal(db, mensal)
    eventos = list(reversed(resumo_operacional["eventos"]))
    calendario_mensal = _construir_calendario_mensal(mensal, resumo_operacional["eventos"])
    return _responder_pdf(
        request,
        "planeamento_clube/mensal_pdf.html",
        {
            "utilizador": utilizador,
            "mensal": mensal,
            "semanais": semanais,
            "eventos": eventos,
            "calendario_mensal": calendario_mensal,
            "resumo_operacional_equipas": resumo_operacional["resumo_equipas"],
            "jogos_do_mes": resumo_operacional["jogos_mes"],
            "estatisticas_operacionais": resumo_operacional["estatisticas"],
            "hoje": date.today(),
        },
        f"planeamento_mensal_{mensal.ano}_{mensal.mes}_{mensal.id}.pdf",
    )


@router.get("/mensal/{mensal_id}/editar", response_class=HTMLResponse)
def form_editar_planeamento_mensal(mensal_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_coordenacao)):

    mensal = db.query(PlaneamentoClubeMensal).filter(PlaneamentoClubeMensal.id == mensal_id).first()
    if not mensal:
        return RedirectResponse(url="/planeamento-clube/anual")

    contexto = _obter_contexto_form_mensal()
    contexto.update({
        "utilizador": utilizador,
        "mensal": mensal,
        "modo": "editar",
    })
    return templates.TemplateResponse(request, "planeamento_clube/mensal_form.html", contexto)


@router.post("/mensal/{mensal_id}/editar")
async def editar_planeamento_mensal(
    mensal_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_coordenacao),
    ano: str = Form(...),
    mes: str = Form(...),
    titulo: str = Form(...),
    objetivos_mes: str = Form(""),
    observacoes: str = Form(""),
    estado: str = Form("rascunho"),
):

    mensal = db.query(PlaneamentoClubeMensal).filter(PlaneamentoClubeMensal.id == mensal_id).first()
    if not mensal:
        return RedirectResponse(url="/planeamento-clube/anual")

    try:
        _atualizar_planeamento_mensal(
            mensal,
            ano,
            mes,
            titulo,
            objetivos_mes,
            observacoes,
            estado,
        )
    except ValueError as erro:
        set_flash(request, str(erro), "error")
        return RedirectResponse(url=f"/planeamento-clube/mensal/{mensal.id}/editar", status_code=303)
    registar_historico_planeamento(db, utilizador, "planeamento_mensal", mensal.id, "editado", mensal.titulo)
    registar_auditoria(db, utilizador, "editar", "planeamento_mensal", mensal.id, mensal.titulo, request)
    db.commit()

    return RedirectResponse(url=f"/planeamento-clube/mensal/{mensal.id}", status_code=303)


@router.post("/mensal/{mensal_id}/eliminar")
async def eliminar_planeamento_mensal(mensal_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_coordenacao)):

    mensal = db.query(PlaneamentoClubeMensal).filter(PlaneamentoClubeMensal.id == mensal_id).first()
    if not mensal:
        return RedirectResponse(url="/planeamento-clube/anual", status_code=303)

    if mensal.planos_semanais:
        return RedirectResponse(url=f"/planeamento-clube/mensal/{mensal_id}?erro=mensal_com_semanais", status_code=303)

    eventos_diretos = db.query(EventoPlaneamentoClube).filter(
        EventoPlaneamentoClube.planeamento_mensal_id == mensal_id,
        EventoPlaneamentoClube.plano_semanal_id.is_(None),
    ).first()
    if eventos_diretos:
        return RedirectResponse(url=f"/planeamento-clube/mensal/{mensal_id}?erro=mensal_com_eventos", status_code=303)

    anual_id = mensal.planeamento_anual_id
    registar_auditoria(db, utilizador, "apagar", "planeamento_mensal", mensal.id, mensal.titulo, request)
    db.delete(mensal)
    db.commit()

    return RedirectResponse(url=f"/planeamento-clube/anual/{anual_id}", status_code=303)


@router.get("/semanal/novo", response_class=HTMLResponse)
def form_novo_plano_semanal(request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_coordenacao)):
    contexto = _obter_contexto_form_semanal()
    contexto.update({
        "utilizador": utilizador,
        "semanal": None,
        "modo": "criar",
        "planeamentos_mensais": db.query(PlaneamentoClubeMensal).order_by(
            PlaneamentoClubeMensal.ano.desc(), PlaneamentoClubeMensal.mes.desc()
        ).all(),
    })
    return templates.TemplateResponse(request, "planeamento_clube/semanal_form.html", contexto)


@router.post("/semanal/novo")
async def criar_plano_semanal_direto(
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_coordenacao),
    planeamento_mensal_id: int = Form(...),
    titulo: str = Form(...),
    data_inicio: str = Form(...),
    data_fim: str = Form(...),
    observacoes: str = Form(""),
    estado: str = Form("rascunho"),
):
    mensal = db.query(PlaneamentoClubeMensal).filter(PlaneamentoClubeMensal.id == planeamento_mensal_id).first()
    if not mensal:
        set_flash(request, "Seleciona um planeamento mensal válido.", "error")
        return RedirectResponse(url="/planeamento-clube/semanal/novo", status_code=303)
    try:
        semanal = _criar_plano_semanal_modelo(planeamento_mensal_id, titulo, data_inicio, data_fim, observacoes, estado)
    except ValueError as erro:
        set_flash(request, str(erro), "error")
        return RedirectResponse(url="/planeamento-clube/semanal/novo", status_code=303)
    db.add(semanal)
    db.flush()
    registar_historico_planeamento(db, utilizador, "plano_semanal", semanal.id, "criado", "Plano criado pela gestão semanal.")
    registar_auditoria(db, utilizador, "criar", "plano_semanal", semanal.id, semanal.titulo, request)
    db.commit()
    return RedirectResponse(url=f"/planeamento-clube/semanal/{semanal.id}", status_code=303)


@router.post("/semanal/{semanal_id}/duplicar")
def duplicar_plano_semanal(semanal_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_coordenacao)):
    origem = db.query(PlanoSemanalClube).filter(PlanoSemanalClube.id == semanal_id).first()
    if not origem:
        return RedirectResponse(url="/planeamento-clube/semanal", status_code=303)
    deslocamento = timedelta(days=7)
    copia = PlanoSemanalClube(
        planeamento_mensal_id=origem.planeamento_mensal_id,
        titulo=f"{origem.titulo} (cópia)",
        data_inicio=origem.data_inicio + deslocamento,
        data_fim=origem.data_fim + deslocamento,
        observacoes=origem.observacoes,
        estado="rascunho",
    )
    db.add(copia)
    db.flush()
    for evento in origem.eventos:
        novo_evento = EventoPlaneamentoClube(
            tipo=evento.tipo, titulo=evento.titulo, descricao=evento.descricao,
            data=evento.data + deslocamento, hora_inicio=evento.hora_inicio, hora_fim=evento.hora_fim,
            planeamento_anual_id=evento.planeamento_anual_id, planeamento_mensal_id=evento.planeamento_mensal_id,
            plano_semanal_id=copia.id, equipa_id=evento.equipa_id, espaco_id=evento.espaco_id,
            treinador_id=evento.treinador_id, aplica_a_todas_equipas=evento.aplica_a_todas_equipas,
            origem=OrigemEventoPlaneamentoClubeEnum.manual, observacoes=evento.observacoes,
        )
        novo_evento.equipas = list(evento.equipas)
        db.add(novo_evento)
    for atribuicao in origem.atribuicoes_espacos:
        db.add(AtribuicaoEspacoSemanal(
            plano_semanal_id=copia.id, espaco_id=atribuicao.espaco_id, equipa_id=atribuicao.equipa_id,
            treinador_id=atribuicao.treinador_id,
            data=atribuicao.data + deslocamento, hora_inicio=atribuicao.hora_inicio, hora_fim=atribuicao.hora_fim,
            tipo_ocupacao=atribuicao.tipo_ocupacao, estado=EstadoAtribuicaoEspacoEnum.rascunho,
            origem=OrigemAtribuicaoEspacoEnum.manual, observacoes=atribuicao.observacoes,
        ))
    registar_historico_planeamento(db, utilizador, "plano_semanal", copia.id, "duplicado", f"Duplicado do plano #{origem.id}.")
    registar_auditoria(db, utilizador, "duplicar", "plano_semanal", copia.id, origem.titulo, request)
    db.commit()
    set_flash(request, "Plano duplicado como rascunho. Confirma datas, equipas e espaços antes de publicar.")
    return RedirectResponse(url=f"/planeamento-clube/semanal/{copia.id}/editar", status_code=303)


@router.post("/mensal/{mensal_id}/semanal/novo")
async def criar_plano_semanal(
    mensal_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_coordenacao),
    titulo: str = Form(...),
    data_inicio: str = Form(...),
    data_fim: str = Form(...),
    observacoes: str = Form(""),
    estado: str = Form("rascunho"),
):

    mensal = db.query(PlaneamentoClubeMensal).filter(PlaneamentoClubeMensal.id == mensal_id).first()
    if not mensal:
        return RedirectResponse(url="/planeamento-clube/anual")

    try:
        semanal = _criar_plano_semanal_modelo(
            mensal_id,
            titulo,
            data_inicio,
            data_fim,
            observacoes,
            estado,
        )
    except ValueError as erro:
        set_flash(request, str(erro), "error")
        return RedirectResponse(url=f"/planeamento-clube/mensal/{mensal_id}", status_code=303)
    db.add(semanal)
    db.flush()
    registar_historico_planeamento(
        db,
        utilizador,
        "plano_semanal",
        semanal.id,
        "criado",
        f"Plano criado a partir do planeamento mensal {mensal_id}.",
    )
    registar_auditoria(
        db,
        utilizador,
        "criar",
        "plano_semanal",
        semanal.id,
        "Plano semanal criado.",
        request,
    )
    db.commit()
    db.refresh(semanal)

    return RedirectResponse(url=f"/planeamento-clube/semanal/{semanal.id}", status_code=303)


@router.get("/semanal/{semanal_id}", response_class=HTMLResponse)
def detalhe_plano_semanal(semanal_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_secretaria)):

    semanal = db.query(PlanoSemanalClube).filter(PlanoSemanalClube.id == semanal_id).first()
    if not semanal:
        return RedirectResponse(url="/planeamento-clube/anual")

    eventos = db.query(EventoPlaneamentoClube).filter(
        EventoPlaneamentoClube.plano_semanal_id == semanal_id
    ).order_by(EventoPlaneamentoClube.data.desc(), EventoPlaneamentoClube.hora_inicio.desc()).all()
    atribuicoes = db.query(AtribuicaoEspacoSemanal).filter(
        AtribuicaoEspacoSemanal.plano_semanal_id == semanal_id
    ).order_by(
        AtribuicaoEspacoSemanal.data.asc(),
        AtribuicaoEspacoSemanal.hora_inicio.asc(),
    ).all()
    calendario_semanal = _construir_calendario_semanal(semanal, eventos, atribuicoes)
    mapa_espacos = construir_mapa_espacos_semanal(atribuicoes)
    grelha_slots = gerar_grelha_slots(db, semanal)
    slots = [slot for dia in grelha_slots["dias"] for slot in dia["slots"]]
    resumo_slots = {
        "livres": sum(1 for slot in slots if not slot["atribuicao"] and not slot["bloqueio"]),
        "atribuidos": sum(1 for slot in slots if slot["atribuicao"] and slot["atribuicao"].equipa_id),
        "pendentes": sum(1 for slot in slots if slot["atribuicao"] and not slot["atribuicao"].equipa_id),
        "bloqueados": sum(1 for slot in slots if slot["bloqueio"]),
    }

    return templates.TemplateResponse(request, "planeamento_clube/semanal_detalhe.html", {
        "utilizador": utilizador,
        "semanal": semanal,
        "estado_visual_plano": _obter_estado_visual_plano_semanal(semanal),
        "eventos": eventos,
        "atribuicoes": atribuicoes,
        "mapa_espacos_operacional": mapa_espacos["mapa"],
        "conflitos_espacos": mapa_espacos["conflitos"],
        "grelha_slots": grelha_slots,
        "resumo_slots": resumo_slots,
        "calendario_semanal": calendario_semanal,
        "pode_gerir": verificar_perfil(utilizador, ["administrador", "coordenador", "superadministrador"]),
        "erro": _obter_mensagem_erro_eliminacao(request.query_params.get("erro")),
    })


@router.get("/semanal/{semanal_id}/pdf")
def exportar_pdf_plano_semanal(
    semanal_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_secretaria),
):
    semanal = db.query(PlanoSemanalClube).filter(PlanoSemanalClube.id == semanal_id).first()
    if not semanal:
        return RedirectResponse(url="/planeamento-clube/anual")
    eventos = db.query(EventoPlaneamentoClube).filter(
        EventoPlaneamentoClube.plano_semanal_id == semanal_id
    ).order_by(EventoPlaneamentoClube.data.asc(), EventoPlaneamentoClube.hora_inicio.asc()).all()
    atribuicoes = db.query(AtribuicaoEspacoSemanal).filter(
        AtribuicaoEspacoSemanal.plano_semanal_id == semanal_id
    ).order_by(AtribuicaoEspacoSemanal.data.asc(), AtribuicaoEspacoSemanal.hora_inicio.asc()).all()
    calendario_semanal = _construir_calendario_semanal(semanal, eventos, atribuicoes)
    mapa_espacos = construir_mapa_espacos_semanal(atribuicoes)
    historico = db.query(HistoricoPlaneamentoClube).filter(
        HistoricoPlaneamentoClube.entidade == "plano_semanal",
        HistoricoPlaneamentoClube.entidade_id == semanal_id,
    ).order_by(HistoricoPlaneamentoClube.criado_em.desc()).limit(20).all()
    return _responder_pdf(
        request,
        "planeamento_clube/semanal_pdf.html",
        {
            "utilizador": utilizador,
            "semanal": semanal,
            "estado_visual_plano": _obter_estado_visual_plano_semanal(semanal),
            "eventos": eventos,
            "atribuicoes": atribuicoes,
            "mapa_espacos_operacional": mapa_espacos["mapa"],
        "conflitos_espacos": mapa_espacos["conflitos"],
        "historico": historico,
            "calendario_semanal": calendario_semanal,
            "hoje": date.today(),
        },
        f"plano_semanal_{semanal.id}_{semanal.data_inicio}.pdf",
    )


@router.get("/semanal/{semanal_id}/editar", response_class=HTMLResponse)
def form_editar_plano_semanal(semanal_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_coordenacao)):

    semanal = db.query(PlanoSemanalClube).filter(PlanoSemanalClube.id == semanal_id).first()
    if not semanal:
        return RedirectResponse(url="/planeamento-clube/anual")

    contexto = _obter_contexto_form_semanal()
    contexto.update({
        "utilizador": utilizador,
        "semanal": semanal,
        "modo": "editar",
    })
    return templates.TemplateResponse(request, "planeamento_clube/semanal_form.html", contexto)


@router.post("/semanal/{semanal_id}/publicar")
def publicar_plano_semanal(
    semanal_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_coordenacao),
):
    semanal = db.query(PlanoSemanalClube).filter(PlanoSemanalClube.id == semanal_id).first()
    if not semanal:
        return RedirectResponse(url="/planeamento-clube/anual", status_code=303)
    conflitos = _obter_conflitos_publicacao(db, semanal)
    if conflitos:
        set_flash(request, f"Não é possível publicar: existem {len(conflitos)} conflito(s) de espaço.", "error")
        return RedirectResponse(url=f"/planeamento-clube/semanal/{semanal_id}", status_code=303)
    semanal.estado = "ativo"
    registar_historico_planeamento(db, utilizador, "plano_semanal", semanal_id, "publicado", "Plano publicado após validação de conflitos.")
    registar_auditoria(db, utilizador, "publicar", "plano_semanal", semanal_id, "Plano semanal publicado.", request)
    db.commit()
    set_flash(request, "Plano semanal publicado e validado.")
    return RedirectResponse(url=f"/planeamento-clube/semanal/{semanal_id}", status_code=303)


@router.post("/semanal/{semanal_id}/retirar-publicacao")
def retirar_publicacao_plano_semanal(
    semanal_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_coordenacao),
):
    semanal = db.query(PlanoSemanalClube).filter(PlanoSemanalClube.id == semanal_id).first()
    if not semanal:
        return RedirectResponse(url="/planeamento-clube/anual", status_code=303)
    semanal.estado = "rascunho"
    registar_historico_planeamento(db, utilizador, "plano_semanal", semanal_id, "retirado_publicacao", "Plano voltou a rascunho.")
    registar_auditoria(db, utilizador, "retirar_publicacao", "plano_semanal", semanal_id, None, request)
    db.commit()
    set_flash(request, "Plano semanal voltou a rascunho.")
    return RedirectResponse(url=f"/planeamento-clube/semanal/{semanal_id}", status_code=303)


@router.post("/semanal/{semanal_id}/editar")
async def editar_plano_semanal(
    semanal_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_coordenacao),
    titulo: str = Form(...),
    data_inicio: str = Form(...),
    data_fim: str = Form(...),
    observacoes: str = Form(""),
    estado: str = Form("rascunho"),
):

    semanal = db.query(PlanoSemanalClube).filter(PlanoSemanalClube.id == semanal_id).first()
    if not semanal:
        return RedirectResponse(url="/planeamento-clube/anual")

    try:
        _atualizar_plano_semanal_modelo(
            semanal,
            titulo,
            data_inicio,
            data_fim,
            observacoes,
            estado,
        )
    except ValueError as erro:
        set_flash(request, str(erro), "error")
        return RedirectResponse(url=f"/planeamento-clube/semanal/{semanal.id}/editar", status_code=303)
    if semanal.estado == "ativo" and _obter_conflitos_publicacao(db, semanal):
        set_flash(request, "Corrige os conflitos de espaço antes de manter o plano publicado.", "error")
        return RedirectResponse(url=f"/planeamento-clube/semanal/{semanal.id}/editar", status_code=303)
    registar_historico_planeamento(db, utilizador, "plano_semanal", semanal.id, "editado", "Dados do plano semanal atualizados.")
    registar_auditoria(db, utilizador, "editar", "plano_semanal", semanal.id, semanal.titulo, request)
    db.commit()

    return RedirectResponse(url=f"/planeamento-clube/semanal/{semanal.id}", status_code=303)


@router.post("/semanal/{semanal_id}/eliminar")
async def eliminar_plano_semanal(semanal_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_coordenacao)):
    semanal = db.query(PlanoSemanalClube).filter(PlanoSemanalClube.id == semanal_id).first()
    if not semanal:
        return RedirectResponse(url="/planeamento-clube/anual", status_code=303)

    atribuicoes = db.query(AtribuicaoEspacoSemanal).filter(
        AtribuicaoEspacoSemanal.plano_semanal_id == semanal_id,
    ).all()
    eventos = db.query(EventoPlaneamentoClube).filter(
        EventoPlaneamentoClube.plano_semanal_id == semanal_id,
    ).all()
    # Algumas marcações antigas foram ligadas à atribuição mas não guardaram o
    # plano semanal no evento. A atribuição continua a ser a fonte de verdade.
    eventos_por_id = {evento.id: evento for evento in eventos}
    for atribuicao in atribuicoes:
        if atribuicao.evento_id and atribuicao.evento_id not in eventos_por_id:
            evento = db.query(EventoPlaneamentoClube).filter(
                EventoPlaneamentoClube.id == atribuicao.evento_id,
            ).first()
            if evento:
                eventos_por_id[evento.id] = evento
    eventos = list(eventos_por_id.values())
    notificacoes_criadas = _notificar_cancelamento_plano_semanal(db, semanal, atribuicoes)

    # Remove eventos e todas as sessões que vieram deste plano. Uma ficha que
    # já tenha exercícios é trabalho técnico do treinador e mantém-se autónoma.
    sessoes_removidas = sessoes_preservadas = 0
    for evento in eventos:
        removidas_evento, preservadas_evento = _eliminar_evento_com_dependencias(
            db,
            evento,
            preservar_sessoes_com_exercicios=True,
        )
        sessoes_removidas += removidas_evento
        sessoes_preservadas += preservadas_evento

    removidas_diretas, preservadas_diretas = _remover_sessoes_do_plano_semanal(
        db,
        semanal_id,
        preservar_sessoes_com_exercicios=True,
    )
    sessoes_removidas += removidas_diretas
    sessoes_preservadas += preservadas_diretas

    mensal_id = semanal.planeamento_mensal_id
    registar_historico_planeamento(
        db,
        utilizador,
        "plano_semanal",
        semanal.id,
        "eliminado",
        f"Plano eliminado com {len(atribuicoes)} marcação(ões) anulada(s), "
        f"{sessoes_removidas} sessão(ões) removida(s) e {sessoes_preservadas} ficha(s) preservada(s).",
    )
    registar_auditoria(
        db,
        utilizador,
        "eliminar",
        "plano_semanal",
        semanal.id,
        f"{len(atribuicoes)} marcação(ões) anulada(s); {sessoes_removidas} sessão(ões) removida(s); "
        f"{sessoes_preservadas} ficha(s) preservada(s); {notificacoes_criadas} notificação(ões) enviada(s).",
        request,
    )
    db.delete(semanal)
    db.commit()

    set_flash(
        request,
        f"Plano semanal eliminado. Foram anuladas {len(atribuicoes)} marcação(ões), removidas {sessoes_removidas} sessão(ões) "
        f"e preservadas {sessoes_preservadas} ficha(s) com exercícios. Foram avisados {notificacoes_criadas} treinador(es).",
    )
    return RedirectResponse(url=f"/planeamento-clube/mensal/{mensal_id}", status_code=303)


@router.post("/semanal/{semanal_id}/sincronizar")
async def sincronizar_plano_semanal(semanal_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_coordenacao)):

    semanal = db.query(PlanoSemanalClube).filter(PlanoSemanalClube.id == semanal_id).first()
    if not semanal:
        return RedirectResponse(url="/planeamento-clube/anual", status_code=303)

    set_flash(request, "O planeamento semanal é apenas logístico e não cria sessões de treino.", "info")
    return RedirectResponse(url=f"/planeamento-clube/semanal/{semanal_id}", status_code=303)


@router.get("/espacos", response_class=HTMLResponse)
def listar_espacos(request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_secretaria)):

    espacos = db.query(EspacoTreino).order_by(EspacoTreino.ativo.desc(), EspacoTreino.nome.asc()).all()
    hoje = date.today()
    semana_atribuicao = db.query(PlanoSemanalClube).filter(
        PlanoSemanalClube.data_inicio <= hoje,
        PlanoSemanalClube.data_fim >= hoje,
    ).order_by(PlanoSemanalClube.data_inicio.desc()).first()
    if not semana_atribuicao:
        semana_atribuicao = db.query(PlanoSemanalClube).filter(
            PlanoSemanalClube.data_inicio >= hoje,
        ).order_by(PlanoSemanalClube.data_inicio.asc()).first()
    return templates.TemplateResponse(request, "planeamento_clube/espacos_lista.html", {
        "utilizador": utilizador,
        "espacos": espacos,
        "semana_atribuicao": semana_atribuicao,
        "pode_gerir": verificar_perfil(utilizador, ["administrador", "coordenador", "superadministrador"]),
    })


@router.get("/atribuicao-espacos", response_class=HTMLResponse)
def painel_atribuicao_espacos(
    request: Request,
    semana_id: int | None = None,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_coordenacao),
):
    """Entrada operacional autónoma para distribuir slots, sem navegar pelos planos."""
    semanais = db.query(PlanoSemanalClube).order_by(PlanoSemanalClube.data_inicio.desc()).all()
    hoje = date.today()
    semanal = next((item for item in semanais if item.id == semana_id), None)
    if not semanal:
        semanal = next(
            (item for item in semanais if item.data_inicio <= hoje <= item.data_fim),
            next((item for item in semanais if item.data_inicio >= hoje), semanais[0] if semanais else None),
        )

    grelha_slots = gerar_grelha_slots(db, semanal) if semanal else None
    slots = [slot for dia in grelha_slots["dias"] for slot in dia["slots"]] if grelha_slots else []
    horarios_slots = sorted({(slot["hora_inicio"], slot["hora_fim"]) for slot in slots})
    slots_por_chave = {}
    for dia in (grelha_slots["dias"] if grelha_slots else []):
        for slot in dia["slots"]:
            chave = f"{dia['data'].isoformat()}|{slot['hora_inicio']}|{slot['hora_fim']}"
            slots_por_chave.setdefault(chave, []).append(slot)
    espacos_com_horario = {slot["espaco"].id for slot in slots}
    espacos_sem_horario = [
        espaco for espaco in (grelha_slots["espacos"] if grelha_slots else [])
        if espaco.id not in espacos_com_horario
    ]
    equipas = db.query(Equipa).order_by(Equipa.nome.asc()).all()
    cores_equipas = construir_cores_equipas(equipas)
    cores_espacos = construir_cores_espacos(grelha_slots["espacos"] if grelha_slots else [])
    equipas_com_atribuicoes = [
        equipa for equipa in equipas
        if any(slot["atribuicao"] and slot["atribuicao"].equipa_id == equipa.id for slot in slots)
    ]
    return templates.TemplateResponse(request, "planeamento_clube/atribuicao_espacos.html", {
        "utilizador": utilizador,
        "semanais": semanais,
        "semanal": semanal,
        "grelha_slots": grelha_slots,
        "horarios_slots": horarios_slots,
        "slots_por_chave": slots_por_chave,
        "espacos_sem_horario": espacos_sem_horario,
        "equipas": equipas,
        "cores_equipas": cores_equipas,
        "cores_espacos": cores_espacos,
        "cor_equipa_neutra": COR_NEUTRA,
        "equipas_com_atribuicoes": equipas_com_atribuicoes,
        "resumo_slots": {
            "livres": sum(1 for slot in slots if not slot["atribuicao"] and not slot["bloqueio"]),
            "ocupados": sum(1 for slot in slots if slot["atribuicao"]),
            "bloqueados": sum(1 for slot in slots if slot["bloqueio"]),
            "rascunhos": sum(
                1 for slot in slots
                if slot["atribuicao"] and slot["atribuicao"].estado == EstadoAtribuicaoEspacoEnum.rascunho
            ),
        },
    })


@router.post("/atribuicao-espacos/gravar")
async def gravar_atribuicoes_rapidas(
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_coordenacao),
):
    """Guarda as escolhas feitas directamente no mapa, sempre como rascunho."""
    try:
        dados = await request.json()
    except ValueError:
        return JSONResponse({"sucesso": False, "erro": "Os dados enviados não são válidos."}, status_code=400)

    try:
        semanal_id = int(dados.get("semana_id"))
    except (TypeError, ValueError):
        return JSONResponse({"sucesso": False, "erro": "A semana seleccionada não é válida."}, status_code=422)

    semanal = db.query(PlanoSemanalClube).filter(PlanoSemanalClube.id == semanal_id).first()
    if not semanal:
        return JSONResponse({"sucesso": False, "erro": "O plano semanal já não existe."}, status_code=404)

    criacoes = dados.get("criacoes", [])
    remover_ids = dados.get("remover_ids", [])
    if not isinstance(criacoes, list) or not isinstance(remover_ids, list):
        return JSONResponse({"sucesso": False, "erro": "As alterações enviadas não são válidas."}, status_code=422)
    if len(criacoes) + len(remover_ids) > 80:
        return JSONResponse({"sucesso": False, "erro": "Guarda até 80 alterações de cada vez."}, status_code=422)

    try:
        ids_remover = {int(item) for item in remover_ids}
    except (TypeError, ValueError):
        return JSONResponse({"sucesso": False, "erro": "Uma atribuição a remover não é válida."}, status_code=422)

    rascunhos_a_remover = []
    if ids_remover:
        rascunhos_a_remover = db.query(AtribuicaoEspacoSemanal).filter(
            AtribuicaoEspacoSemanal.id.in_(ids_remover),
            AtribuicaoEspacoSemanal.plano_semanal_id == semanal.id,
            AtribuicaoEspacoSemanal.estado == EstadoAtribuicaoEspacoEnum.rascunho,
        ).all()
        if len(rascunhos_a_remover) != len(ids_remover):
            return JSONResponse({
                "sucesso": False,
                "erro": "Só é possível remover do mapa as atribuições ainda não enviadas.",
            }, status_code=422)

    try:
        for atribuicao in rascunhos_a_remover:
            db.delete(atribuicao)
        db.flush()

        criadas = []
        for indice, item in enumerate(criacoes, start=1):
            if not isinstance(item, dict):
                raise ValueError(f"A atribuição {indice} não é válida.")
            espaco_id = _converter_id(str(item.get("espaco_id", "")), "Espaço", obrigatorio=True)
            equipa_id = _converter_id(str(item.get("equipa_id", "")), "Equipa", obrigatorio=True)
            data_atribuicao = str(item.get("data", ""))
            hora_inicio = normalizar_hora(str(item.get("hora_inicio", "")), permitir_vazio=False)
            hora_fim = normalizar_hora(str(item.get("hora_fim", "")), permitir_vazio=False)
            tipo_ocupacao = str(item.get("tipo_ocupacao", TipoOcupacaoEspacoEnum.treino_equipa.value))
            erro = _validar_dados_atribuicao(semanal, data_atribuicao, hora_inicio, hora_fim)
            if erro:
                raise ValueError(f"A atribuição {indice}: {erro}")

            espaco = db.query(EspacoTreino).filter(EspacoTreino.id == espaco_id).first()
            equipa = db.query(Equipa).filter(Equipa.id == equipa_id).first()
            if not espaco or not equipa:
                raise ValueError(f"A atribuição {indice} refere um espaço ou equipa que já não existe.")
            if getattr(espaco, "clube_id", semanal.clube_id) != semanal.clube_id or getattr(equipa, "clube_id", semanal.clube_id) != semanal.clube_id:
                raise ValueError(f"A atribuição {indice} tem de usar dados do mesmo clube.")

            data_convertida = _converter_data(data_atribuicao, "Data da atribuição")
            conflitos = validar_reserva(
                db,
                espaco_id=espaco_id,
                equipa_id=equipa_id,
                treinador_id=None,
                data_slot=data_convertida,
                hora_inicio=hora_inicio,
                hora_fim=hora_fim,
            )
            if conflitos:
                raise ValueError(f"A atribuição {indice}: {' '.join(conflitos)}")

            atribuicao = _criar_atribuicao(
                semanal.id,
                str(espaco_id),
                str(equipa_id),
                "",
                "",
                data_atribuicao,
                hora_inicio,
                hora_fim,
                tipo_ocupacao,
                EstadoAtribuicaoEspacoEnum.rascunho.value,
                OrigemAtribuicaoEspacoEnum.manual.value,
                "",
            )
            atribuicao.clube_id = semanal.clube_id
            db.add(atribuicao)
            db.flush()
            criadas.append(atribuicao)
    except ValueError as erro:
        db.rollback()
        return JSONResponse({"sucesso": False, "erro": str(erro)}, status_code=422)

    if criadas or rascunhos_a_remover:
        registar_historico_planeamento(
            db,
            utilizador,
            "plano_semanal",
            semanal.id,
            "atribuicoes_atualizadas",
            f"Mapa actualizado: {len(criadas)} atribuições criadas e {len(rascunhos_a_remover)} removidas.",
        )
        registar_auditoria(
            db,
            utilizador,
            "atualizar",
            "atribuicoes_espaco_semanais",
            semanal.id,
            f"{len(criadas)} rascunhos criados; {len(rascunhos_a_remover)} removidos.",
            request,
        )
    db.commit()
    return JSONResponse({
        "sucesso": True,
        "mensagem": f"Foram guardadas {len(criadas)} atribuições em rascunho.",
        "criadas": len(criadas),
        "removidas": len(rascunhos_a_remover),
    })


@router.post("/atribuicao-espacos/enviar")
async def enviar_atribuicoes_aos_treinadores(
    request: Request,
    semana_id: int = Form(...),
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_coordenacao),
):
    """Publica rascunhos de espaços e só então cria as previsões nas agendas."""
    semanal = db.query(PlanoSemanalClube).filter(PlanoSemanalClube.id == semana_id).first()
    if not semanal:
        return RedirectResponse(url="/planeamento-clube/atribuicao-espacos", status_code=303)

    conflitos = _obter_conflitos_publicacao(db, semanal)
    if conflitos:
        set_flash(request, f"Não é possível enviar: existem {len(conflitos)} conflito(s) de espaço.", "error")
        return RedirectResponse(url=f"/planeamento-clube/atribuicao-espacos?semana_id={semana_id}", status_code=303)

    rascunhos = db.query(AtribuicaoEspacoSemanal).filter(
        AtribuicaoEspacoSemanal.plano_semanal_id == semanal.id,
        AtribuicaoEspacoSemanal.estado == EstadoAtribuicaoEspacoEnum.rascunho,
    ).order_by(AtribuicaoEspacoSemanal.data, AtribuicaoEspacoSemanal.hora_inicio).all()
    if not rascunhos:
        set_flash(request, "Não existem atribuições por enviar nesta semana.", "info")
        return RedirectResponse(url=f"/planeamento-clube/atribuicao-espacos?semana_id={semana_id}", status_code=303)

    mensagens = []
    notificacoes_criadas = 0
    for atribuicao in rascunhos:
        atribuicao.estado = EstadoAtribuicaoEspacoEnum.publicado
        mensagens.append(sincronizar_atribuicao_com_agenda(db, atribuicao))
        if atribuicao.equipa:
            renumerar_treinos_equipa(db, atribuicao.equipa_id)
            tipo_treino = "Treino físico" if atribuicao.tipo_ocupacao == TipoOcupacaoEspacoEnum.treino_fisico else "Treino"
            notificacoes_criadas += criar_notificacoes_para_equipa(
                db,
                atribuicao.equipa,
                f"{tipo_treino} atualizado",
                f"{atribuicao.data.strftime('%d/%m/%Y')} · {atribuicao.hora_inicio}–{atribuicao.hora_fim} · {atribuicao.espaco.nome}",
                f"/calendario?equipa_id={atribuicao.equipa_id}",
            )
    registar_historico_planeamento(
        db,
        utilizador,
        "plano_semanal",
        semanal.id,
        "atribuicoes_enviadas",
        f"Foram enviadas {len(rascunhos)} atribuições aos treinadores; {notificacoes_criadas} notificações criadas.",
    )
    registar_auditoria(
        db,
        utilizador,
        "publicar",
        "atribuicoes_espaco_semanais",
        semanal.id,
        f"{len(rascunhos)} atribuições enviadas aos treinadores.",
        request,
    )
    db.commit()
    atualizadas = sum("treino técnico coincidente" in mensagem for mensagem in mensagens)
    set_flash(
        request,
        f"Foram enviadas {len(rascunhos)} atribuições. {atualizadas} treino(s) técnico(s) receberam o local automaticamente.",
    )
    return RedirectResponse(url=f"/planeamento-clube/atribuicao-espacos?semana_id={semana_id}", status_code=303)


@router.get("/atribuicao-espacos/pdf")
def exportar_pdf_atribuicao_espacos(
    request: Request,
    semana_id: int,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_coordenacao),
):
    """Exporta a distribuição semanal numa grelha simples por equipa."""
    semanal = db.query(PlanoSemanalClube).filter(PlanoSemanalClube.id == semana_id).first()
    if not semanal:
        return RedirectResponse(url="/planeamento-clube/atribuicao-espacos", status_code=303)

    equipas = db.query(Equipa).order_by(Equipa.nome.asc()).all()
    atribuicoes = db.query(AtribuicaoEspacoSemanal).filter(
        AtribuicaoEspacoSemanal.plano_semanal_id == semanal.id,
        AtribuicaoEspacoSemanal.estado != EstadoAtribuicaoEspacoEnum.cancelado,
    ).all()
    quadro = construir_quadro_atribuicoes(semanal, equipas, atribuicoes)
    return _responder_pdf(
        request,
        "planeamento_clube/atribuicao_espacos_pdf.html",
        {
            "utilizador": utilizador,
            "semanal": semanal,
            "quadro": quadro,
            "data_exportacao": datetime.now().strftime("%d/%m/%Y %H:%M"),
        },
        f"atribuicao_espacos_{semanal.data_inicio.isoformat()}.pdf",
    )


@router.get("/espacos/novo", response_class=HTMLResponse)
def form_novo_espaco(request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_coordenacao)):

    contexto = _obter_contexto_form_espaco()
    contexto.update({
        "utilizador": utilizador,
        "espaco": None,
        "modo": "criar",
    })
    return templates.TemplateResponse(request, "planeamento_clube/espaco_form.html", contexto)


@router.post("/espacos/novo")
async def criar_espaco(
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_coordenacao),
    nome: str = Form(...),
    tipo: str = Form(...),
    localizacao: str = Form(""),
    capacidade: str = Form(""),
    ativo: str = Form("true"),
    observacoes: str = Form(""),
    dia_semana: str = Form(""),
    hora_inicio_slot: str = Form(""),
    hora_fim_slot: str = Form(""),
    duracao_slot_minutos: int = Form(90),
    dias_repetir: list[str] = Form([]),
):

    try:
        espaco = _criar_espaco(nome, tipo, localizacao, capacidade, ativo, observacoes)
    except ValueError as erro:
        set_flash(request, str(erro), "error")
        return RedirectResponse(url="/planeamento-clube/espacos/novo", status_code=303)
    db.add(espaco)
    db.flush()
    if any((dia_semana, hora_inicio_slot, hora_fim_slot)):
        inicio = normalizar_hora(hora_inicio_slot, permitir_vazio=False)
        fim = normalizar_hora(hora_fim_slot, permitir_vazio=False)
        if not dia_semana.isdigit() or int(dia_semana) not in range(7) or not inicio or not fim or not hora_eh_anterior(inicio, fim):
            db.rollback()
            set_flash(request, "A primeira disponibilidade deve indicar dia e um intervalo horário válido.", "error")
            return RedirectResponse(url="/planeamento-clube/espacos/novo", status_code=303)
        if not 15 <= duracao_slot_minutos <= 360:
            db.rollback()
            set_flash(request, "A duração de cada slot deve estar entre 15 e 360 minutos.", "error")
            return RedirectResponse(url="/planeamento-clube/espacos/novo", status_code=303)

        dias = {int(dia_semana)}
        dias.update(int(dia) for dia in dias_repetir if dia.isdigit() and int(dia) in range(7))
        for dia in sorted(dias):
            db.add(DisponibilidadeEspacoTreino(
                espaco_id=espaco.id, dia_semana=dia, hora_inicio=inicio,
                hora_fim=fim, duracao_slot_minutos=duracao_slot_minutos,
            ))
    db.commit()
    db.refresh(espaco)

    return RedirectResponse(url=f"/planeamento-clube/espacos/{espaco.id}", status_code=303)


@router.get("/espacos/{espaco_id}", response_class=HTMLResponse)
def detalhe_espaco(espaco_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_secretaria)):

    espaco = db.query(EspacoTreino).filter(EspacoTreino.id == espaco_id).first()
    if not espaco:
        return RedirectResponse(url="/planeamento-clube/espacos")

    hoje = date.today()
    atribuicoes_associadas = db.query(AtribuicaoEspacoSemanal).filter(
        AtribuicaoEspacoSemanal.espaco_id == espaco_id,
        AtribuicaoEspacoSemanal.data >= hoje,
    ).order_by(
        AtribuicaoEspacoSemanal.data.asc(),
        AtribuicaoEspacoSemanal.hora_inicio.asc(),
    ).all()
    ocupacao_recente = db.query(AtribuicaoEspacoSemanal).filter(
        AtribuicaoEspacoSemanal.espaco_id == espaco_id,
        AtribuicaoEspacoSemanal.data < hoje,
    ).order_by(
        AtribuicaoEspacoSemanal.data.desc(),
        AtribuicaoEspacoSemanal.hora_inicio.desc(),
    ).limit(10).all()

    return templates.TemplateResponse(request, "planeamento_clube/espaco_detalhe.html", {
        "utilizador": utilizador,
        "espaco": espaco,
        "atribuicoes_associadas": atribuicoes_associadas,
        "ocupacao_recente": ocupacao_recente,
        "pode_gerir": verificar_perfil(utilizador, ["administrador", "coordenador", "superadministrador"]),
        "erro": _obter_mensagem_erro_eliminacao(
            "espaco_com_atribuicoes" if request.query_params.get("erro") == "nao_pode_eliminar_com_atribuicoes" else request.query_params.get("erro")
        ),
    })


@router.get("/espacos/{espaco_id}/editar", response_class=HTMLResponse)
def form_editar_espaco(espaco_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_coordenacao)):

    espaco = db.query(EspacoTreino).filter(EspacoTreino.id == espaco_id).first()
    if not espaco:
        return RedirectResponse(url="/planeamento-clube/espacos")

    contexto = _obter_contexto_form_espaco()
    contexto.update({
        "utilizador": utilizador,
        "espaco": espaco,
        "modo": "editar",
    })
    return templates.TemplateResponse(request, "planeamento_clube/espaco_form.html", contexto)


@router.post("/espacos/{espaco_id}/editar")
async def editar_espaco(
    espaco_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_coordenacao),
    nome: str = Form(...),
    tipo: str = Form(...),
    localizacao: str = Form(""),
    capacidade: str = Form(""),
    ativo: str = Form("true"),
    observacoes: str = Form(""),
):

    espaco = db.query(EspacoTreino).filter(EspacoTreino.id == espaco_id).first()
    if not espaco:
        return RedirectResponse(url="/planeamento-clube/espacos")

    try:
        _atualizar_espaco(espaco, nome, tipo, localizacao, capacidade, ativo, observacoes)
    except ValueError as erro:
        set_flash(request, str(erro), "error")
        return RedirectResponse(url=f"/planeamento-clube/espacos/{espaco.id}/editar", status_code=303)
    db.commit()

    return RedirectResponse(url=f"/planeamento-clube/espacos/{espaco.id}", status_code=303)


@router.post("/espacos/{espaco_id}/eliminar")
async def eliminar_espaco(espaco_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_coordenacao)):

    espaco = db.query(EspacoTreino).filter(EspacoTreino.id == espaco_id).first()
    if not espaco:
        return RedirectResponse(url="/planeamento-clube/espacos", status_code=303)

    tem_atribuicoes = db.query(AtribuicaoEspacoSemanal).filter(
        AtribuicaoEspacoSemanal.espaco_id == espaco_id
    ).first()
    if tem_atribuicoes:
        return RedirectResponse(
            url=f"/planeamento-clube/espacos/{espaco_id}?erro=espaco_com_atribuicoes",
            status_code=303,
        )

    db.delete(espaco)
    db.commit()

    return RedirectResponse(url="/planeamento-clube/espacos", status_code=303)


@router.post("/espacos/{espaco_id}/disponibilidades")
def criar_disponibilidade_espaco(
    espaco_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_coordenacao),
    dia_semana: int = Form(...),
    hora_inicio: str = Form(...),
    hora_fim: str = Form(...),
    duracao_slot_minutos: int = Form(90),
    dias_repetir: list[str] = Form([]),
):
    espaco = db.query(EspacoTreino).filter(EspacoTreino.id == espaco_id).first()
    inicio = normalizar_hora(hora_inicio, permitir_vazio=False)
    fim = normalizar_hora(hora_fim, permitir_vazio=False)
    if not espaco or dia_semana not in range(7) or not inicio or not fim or not hora_eh_anterior(inicio, fim):
        set_flash(request, "A disponibilidade indicada não é válida.", "error")
        return RedirectResponse(url=f"/planeamento-clube/espacos/{espaco_id}", status_code=303)
    if duracao_slot_minutos < 15 or duracao_slot_minutos > 360:
        set_flash(request, "A duração do slot deve estar entre 15 e 360 minutos.", "error")
        return RedirectResponse(url=f"/planeamento-clube/espacos/{espaco_id}", status_code=303)
    dias = {dia_semana}
    for valor in dias_repetir:
        if valor.isdigit() and int(valor) in range(7):
            dias.add(int(valor))
    for dia in sorted(dias):
        db.add(DisponibilidadeEspacoTreino(
            espaco_id=espaco.id, dia_semana=dia, hora_inicio=inicio,
            hora_fim=fim, duracao_slot_minutos=duracao_slot_minutos,
        ))
    registar_auditoria(db, utilizador, "criar", "disponibilidade_espaco", espaco.id, f"Dia {dia_semana}: {inicio}-{fim}", request)
    db.commit()
    set_flash(request, f"Disponibilidade adicionada a {len(dias)} dia(s). Os slots já ficam visíveis nas semanas abrangidas.")
    return RedirectResponse(url=f"/planeamento-clube/espacos/{espaco_id}", status_code=303)


@router.post("/espacos/disponibilidades/{disponibilidade_id}/editar")
def editar_disponibilidade_espaco(
    disponibilidade_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_coordenacao),
    dia_semana: int = Form(...),
    hora_inicio: str = Form(...),
    hora_fim: str = Form(...),
    duracao_slot_minutos: int = Form(90),
):
    item = db.query(DisponibilidadeEspacoTreino).filter(DisponibilidadeEspacoTreino.id == disponibilidade_id).first()
    inicio = normalizar_hora(hora_inicio, permitir_vazio=False)
    fim = normalizar_hora(hora_fim, permitir_vazio=False)
    if not item or dia_semana not in range(7) or not inicio or not fim or not hora_eh_anterior(inicio, fim) or not 15 <= duracao_slot_minutos <= 360:
        set_flash(request, "A disponibilidade indicada não é válida.", "error")
        return RedirectResponse(url=f"/planeamento-clube/espacos/{item.espaco_id if item else ''}", status_code=303)
    item.dia_semana, item.hora_inicio, item.hora_fim = dia_semana, inicio, fim
    item.duracao_slot_minutos = duracao_slot_minutos
    registar_auditoria(db, utilizador, "editar", "disponibilidade_espaco", item.espaco_id, f"Dia {dia_semana}: {inicio}-{fim}", request)
    db.commit()
    set_flash(request, "Disponibilidade atualizada.")
    return RedirectResponse(url=f"/planeamento-clube/espacos/{item.espaco_id}", status_code=303)


@router.post("/espacos/disponibilidades/{disponibilidade_id}/eliminar")
def eliminar_disponibilidade_espaco(
    disponibilidade_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_coordenacao),
):
    item = db.query(DisponibilidadeEspacoTreino).filter(DisponibilidadeEspacoTreino.id == disponibilidade_id).first()
    if not item:
        return RedirectResponse(url="/planeamento-clube/espacos", status_code=303)
    espaco_id = item.espaco_id
    db.delete(item)
    db.commit()
    return RedirectResponse(url=f"/planeamento-clube/espacos/{espaco_id}", status_code=303)


@router.post("/espacos/{espaco_id}/indisponibilidades")
def criar_indisponibilidade_espaco(
    espaco_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_coordenacao),
    data_inicio: str = Form(...),
    data_fim: str = Form(...),
    hora_inicio: str = Form(""),
    hora_fim: str = Form(""),
    motivo: str = Form(""),
):
    espaco = db.query(EspacoTreino).filter(EspacoTreino.id == espaco_id).first()
    try:
        inicio_data, fim_data = _validar_intervalo_datas(data_inicio, data_fim, "bloqueio")
        inicio_hora = normalizar_hora(hora_inicio) if hora_inicio else None
        fim_hora = normalizar_hora(hora_fim) if hora_fim else None
        if bool(inicio_hora) != bool(fim_hora) or (inicio_hora and not hora_eh_anterior(inicio_hora, fim_hora)):
            raise ValueError("Preenche as duas horas com um intervalo válido, ou deixa ambas vazias.")
    except ValueError as erro:
        set_flash(request, str(erro), "error")
        return RedirectResponse(url=f"/planeamento-clube/espacos/{espaco_id}", status_code=303)
    if not espaco:
        return RedirectResponse(url="/planeamento-clube/espacos", status_code=303)
    db.add(IndisponibilidadeEspacoTreino(
        espaco_id=espaco.id, data_inicio=inicio_data, data_fim=fim_data,
        hora_inicio=inicio_hora, hora_fim=fim_hora, motivo=motivo or None,
    ))
    registar_auditoria(db, utilizador, "criar", "indisponibilidade_espaco", espaco.id, motivo, request)
    db.commit()
    set_flash(request, "Período de indisponibilidade registado.")
    return RedirectResponse(url=f"/planeamento-clube/espacos/{espaco_id}", status_code=303)


@router.post("/espacos/indisponibilidades/{indisponibilidade_id}/eliminar")
def eliminar_indisponibilidade_espaco(
    indisponibilidade_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_coordenacao),
):
    item = db.query(IndisponibilidadeEspacoTreino).filter(IndisponibilidadeEspacoTreino.id == indisponibilidade_id).first()
    if not item:
        return RedirectResponse(url="/planeamento-clube/espacos", status_code=303)
    espaco_id = item.espaco_id
    db.delete(item)
    db.commit()
    return RedirectResponse(url=f"/planeamento-clube/espacos/{espaco_id}", status_code=303)


@router.get("/semanal/{semanal_id}/espacos", response_class=HTMLResponse)
def listar_ocupacao_semanal_espacos(semanal_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_secretaria)):

    semanal = db.query(PlanoSemanalClube).filter(PlanoSemanalClube.id == semanal_id).first()
    if not semanal:
        return RedirectResponse(url="/planeamento-clube/anual")

    atribuicoes = db.query(AtribuicaoEspacoSemanal).filter(
        AtribuicaoEspacoSemanal.plano_semanal_id == semanal_id
    ).order_by(
        AtribuicaoEspacoSemanal.data.asc(),
        AtribuicaoEspacoSemanal.hora_inicio.asc(),
        AtribuicaoEspacoSemanal.espaco_id.asc(),
    ).all()

    return templates.TemplateResponse(request, "planeamento_clube/espacos_lista.html", {
        "utilizador": utilizador,
        "espacos": db.query(EspacoTreino).order_by(EspacoTreino.nome).all(),
        "semanal": semanal,
        "atribuicoes_semanais": atribuicoes,
        "pode_gerir": verificar_perfil(utilizador, ["administrador", "coordenador", "superadministrador"]),
    })


@router.get("/semanal/{semanal_id}/atribuicoes/nova", response_class=HTMLResponse)
def form_nova_atribuicao(semanal_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_coordenacao)):

    semanal = db.query(PlanoSemanalClube).filter(PlanoSemanalClube.id == semanal_id).first()
    if not semanal:
        return RedirectResponse(url="/planeamento-clube/anual")

    contexto = _preparar_atribuicao_form(db, utilizador, "criar", semanal, None)
    contexto["dados_formulario"] = {
        "espaco_id": request.query_params.get("espaco_id", ""),
        "data_atribuicao": request.query_params.get("data", ""),
        "hora_inicio": request.query_params.get("hora_inicio", ""),
        "hora_fim": request.query_params.get("hora_fim", ""),
    }
    return templates.TemplateResponse(request, "planeamento_clube/atribuicao_form.html", contexto)


@router.post("/semanal/{semanal_id}/atribuicoes/nova")
async def criar_atribuicao(
    semanal_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_coordenacao),
    espaco_id: str = Form(...),
    equipa_id: str = Form(""),
    treinador_id: str = Form(""),
    evento_id: str = Form(""),
    data_atribuicao: str = Form(...),
    hora_inicio: str = Form(...),
    hora_fim: str = Form(...),
    tipo_ocupacao: str = Form(...),
    estado: str = Form("rascunho"),
    origem: str = Form("manual"),
    observacoes: str = Form(""),
):

    semanal = db.query(PlanoSemanalClube).filter(PlanoSemanalClube.id == semanal_id).first()
    if not semanal:
        return RedirectResponse(url="/planeamento-clube/anual")
    hora_inicio = normalizar_hora(hora_inicio, permitir_vazio=False) or hora_inicio
    hora_fim = normalizar_hora(hora_fim, permitir_vazio=False) or hora_fim

    dados_formulario = {
        "espaco_id": espaco_id,
        "equipa_id": equipa_id,
        "treinador_id": treinador_id,
        "evento_id": evento_id,
        "data_atribuicao": data_atribuicao,
        "hora_inicio": hora_inicio,
        "hora_fim": hora_fim,
        "tipo_ocupacao": tipo_ocupacao,
        "estado": estado,
        "origem": origem,
        "observacoes": observacoes,
    }
    erro_validacao = _validar_dados_atribuicao(semanal, data_atribuicao, hora_inicio, hora_fim)
    if erro_validacao:
        contexto = _preparar_atribuicao_form(db, utilizador, "criar", semanal, None, erro_validacao, dados_formulario)
        return templates.TemplateResponse(request, "planeamento_clube/atribuicao_form.html", contexto, status_code=400)

    try:
        espaco_id_convertido = _converter_id(espaco_id, "Espaço", obrigatorio=True)
        equipa_id_convertido = _converter_id(equipa_id, "Equipa")
        treinador_id_convertido = _converter_id(treinador_id, "Treinador")
        data_convertida = _converter_data(data_atribuicao, "Data da atribuição")
    except ValueError as erro:
        contexto = _preparar_atribuicao_form(db, utilizador, "criar", semanal, None, str(erro), dados_formulario)
        return templates.TemplateResponse(request, "planeamento_clube/atribuicao_form.html", contexto, status_code=400)

    conflitos = validar_reserva(
        db, espaco_id=espaco_id_convertido, equipa_id=equipa_id_convertido,
        treinador_id=treinador_id_convertido, data_slot=data_convertida,
        hora_inicio=hora_inicio, hora_fim=hora_fim,
    )
    if conflitos:
        erro = " ".join(conflitos)
        contexto = _preparar_atribuicao_form(db, utilizador, "criar", semanal, None, erro, dados_formulario)
        return templates.TemplateResponse(request, "planeamento_clube/atribuicao_form.html", contexto, status_code=400)

    try:
        atribuicao = _criar_atribuicao(
            semanal_id,
            espaco_id,
            equipa_id,
            treinador_id,
            evento_id,
            data_atribuicao,
            hora_inicio,
            hora_fim,
            tipo_ocupacao,
            estado,
            origem,
            observacoes,
        )
    except ValueError as erro:
        contexto = _preparar_atribuicao_form(db, utilizador, "criar", semanal, None, str(erro), dados_formulario)
        return templates.TemplateResponse(request, "planeamento_clube/atribuicao_form.html", contexto, status_code=400)
    db.add(atribuicao)
    db.flush()
    mensagem_sincronizacao = sincronizar_atribuicao_com_agenda(db, atribuicao)
    if atribuicao.equipa_id:
        renumerar_treinos_equipa(db, atribuicao.equipa_id)
    registar_historico_planeamento(db, utilizador, "plano_semanal", semanal.id, "reserva_criada", f"{data_convertida} {hora_inicio}-{hora_fim}.")
    registar_auditoria(db, utilizador, "criar", "atribuicao_espaco_semanal", atribuicao.id, observacoes, request)
    db.commit()
    db.refresh(atribuicao)

    set_flash(request, mensagem_sincronizacao, "info")
    return RedirectResponse(url=f"/planeamento-clube/atribuicoes/{atribuicao.id}", status_code=303)


@router.get("/atribuicoes/{atribuicao_id}", response_class=HTMLResponse)
def detalhe_atribuicao(atribuicao_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_secretaria)):

    atribuicao = db.query(AtribuicaoEspacoSemanal).filter(AtribuicaoEspacoSemanal.id == atribuicao_id).first()
    if not atribuicao:
        return RedirectResponse(url="/planeamento-clube/anual")

    return templates.TemplateResponse(request, "planeamento_clube/atribuicao_detalhe.html", {
        "utilizador": utilizador,
        "atribuicao": atribuicao,
        "pode_gerir": verificar_perfil(utilizador, ["administrador", "coordenador", "superadministrador"]),
    })


@router.get("/atribuicoes/{atribuicao_id}/editar", response_class=HTMLResponse)
def form_editar_atribuicao(atribuicao_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_coordenacao)):

    atribuicao = db.query(AtribuicaoEspacoSemanal).filter(AtribuicaoEspacoSemanal.id == atribuicao_id).first()
    if not atribuicao:
        return RedirectResponse(url="/planeamento-clube/anual")

    contexto = _preparar_atribuicao_form(
        db,
        utilizador,
        "editar",
        atribuicao.plano_semanal,
        atribuicao,
    )
    return templates.TemplateResponse(request, "planeamento_clube/atribuicao_form.html", contexto)


@router.post("/atribuicoes/{atribuicao_id}/editar")
async def editar_atribuicao(
    atribuicao_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_coordenacao),
    espaco_id: str = Form(...),
    equipa_id: str = Form(""),
    treinador_id: str = Form(""),
    evento_id: str = Form(""),
    data_atribuicao: str = Form(...),
    hora_inicio: str = Form(...),
    hora_fim: str = Form(...),
    tipo_ocupacao: str = Form(...),
    estado: str = Form("rascunho"),
    origem: str = Form("manual"),
    observacoes: str = Form(""),
):

    atribuicao = db.query(AtribuicaoEspacoSemanal).filter(AtribuicaoEspacoSemanal.id == atribuicao_id).first()
    if not atribuicao:
        return RedirectResponse(url="/planeamento-clube/anual")
    hora_inicio = normalizar_hora(hora_inicio, permitir_vazio=False) or hora_inicio
    hora_fim = normalizar_hora(hora_fim, permitir_vazio=False) or hora_fim

    semanal = atribuicao.plano_semanal
    dados_formulario = {
        "espaco_id": espaco_id,
        "equipa_id": equipa_id,
        "treinador_id": treinador_id,
        "evento_id": evento_id,
        "data_atribuicao": data_atribuicao,
        "hora_inicio": hora_inicio,
        "hora_fim": hora_fim,
        "tipo_ocupacao": tipo_ocupacao,
        "estado": estado,
        "origem": origem,
        "observacoes": observacoes,
    }
    erro_validacao = _validar_dados_atribuicao(semanal, data_atribuicao, hora_inicio, hora_fim)
    if erro_validacao:
        contexto = _preparar_atribuicao_form(
            db,
            utilizador,
            "editar",
            semanal,
            atribuicao,
            erro_validacao,
            dados_formulario,
        )
        return templates.TemplateResponse(request, "planeamento_clube/atribuicao_form.html", contexto, status_code=400)

    try:
        espaco_id_convertido = _converter_id(espaco_id, "Espaço", obrigatorio=True)
        equipa_id_convertido = _converter_id(equipa_id, "Equipa")
        treinador_id_convertido = _converter_id(treinador_id, "Treinador")
        data_convertida = _converter_data(data_atribuicao, "Data da atribuição")
    except ValueError as erro:
        contexto = _preparar_atribuicao_form(
            db,
            utilizador,
            "editar",
            semanal,
            atribuicao,
            str(erro),
            dados_formulario,
        )
        return templates.TemplateResponse(request, "planeamento_clube/atribuicao_form.html", contexto, status_code=400)

    conflitos = validar_reserva(
        db, espaco_id=espaco_id_convertido, equipa_id=equipa_id_convertido,
        treinador_id=treinador_id_convertido, data_slot=data_convertida,
        hora_inicio=hora_inicio, hora_fim=hora_fim, excluir_id=atribuicao.id,
    )
    if conflitos:
        erro = " ".join(conflitos)
        contexto = _preparar_atribuicao_form(
            db,
            utilizador,
            "editar",
            semanal,
            atribuicao,
            erro,
            dados_formulario,
        )
        return templates.TemplateResponse(request, "planeamento_clube/atribuicao_form.html", contexto, status_code=400)

    equipa_id_anterior = atribuicao.equipa_id
    try:
        _atualizar_atribuicao(
            atribuicao,
            semanal.id,
            espaco_id,
            equipa_id,
            treinador_id,
            evento_id,
            data_atribuicao,
            hora_inicio,
            hora_fim,
            tipo_ocupacao,
            estado,
            origem,
            observacoes,
        )
    except ValueError as erro:
        contexto = _preparar_atribuicao_form(
            db,
            utilizador,
            "editar",
            semanal,
            atribuicao,
            str(erro),
            dados_formulario,
        )
        return templates.TemplateResponse(request, "planeamento_clube/atribuicao_form.html", contexto, status_code=400)
    mensagem_sincronizacao = sincronizar_atribuicao_com_agenda(db, atribuicao)
    for equipa_id in {equipa_id_anterior, atribuicao.equipa_id} - {None}:
        renumerar_treinos_equipa(db, equipa_id)
    registar_historico_planeamento(db, utilizador, "plano_semanal", semanal.id, "reserva_alterada", f"{data_convertida} {hora_inicio}-{hora_fim}.")
    registar_auditoria(db, utilizador, "editar", "atribuicao_espaco_semanal", atribuicao.id, observacoes, request)
    db.commit()

    set_flash(request, mensagem_sincronizacao, "info")
    return RedirectResponse(url=f"/planeamento-clube/atribuicoes/{atribuicao.id}", status_code=303)


@router.post("/atribuicoes/{atribuicao_id}/eliminar")
async def eliminar_atribuicao(
    atribuicao_id: int,
    request: Request,
    retorno: str = Form(""),
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_coordenacao),
):
    atribuicao = db.query(AtribuicaoEspacoSemanal).filter(AtribuicaoEspacoSemanal.id == atribuicao_id).first()
    if not atribuicao:
        return RedirectResponse(url="/planeamento-clube/anual", status_code=303)

    semanal_id = atribuicao.plano_semanal_id
    equipa_id = atribuicao.equipa_id
    notificacoes_criadas = _notificar_cancelamento_atribuicao(db, atribuicao)
    evento = atribuicao.evento
    if evento:
        outras_atribuicoes = db.query(AtribuicaoEspacoSemanal).filter(
            AtribuicaoEspacoSemanal.evento_id == evento.id,
            AtribuicaoEspacoSemanal.id != atribuicao.id,
            AtribuicaoEspacoSemanal.estado != EstadoAtribuicaoEspacoEnum.cancelado,
        ).first()
        if outras_atribuicoes:
            atribuicao.evento_id = None
        else:
            _eliminar_evento_com_dependencias(db, evento)
    registar_historico_planeamento(db, utilizador, "plano_semanal", semanal_id, "reserva_anulada", f"Reserva #{atribuicao.id} anulada.")
    registar_auditoria(db, utilizador, "anular", "atribuicao_espaco_semanal", atribuicao.id, f"{notificacoes_criadas} notificação(ões) enviada(s).", request)
    db.delete(atribuicao)
    if equipa_id:
        renumerar_treinos_equipa(db, equipa_id)
    db.commit()

    set_flash(request, f"Marcação anulada. Foram avisados {notificacoes_criadas} treinador(es).")
    return RedirectResponse(
        url=_destino_retorno_seguro(request, retorno, f"/planeamento-clube/semanal/{semanal_id}"),
        status_code=303,
    )


@router.get("/indisponibilidades-treinador", response_class=HTMLResponse)
def listar_indisponibilidades_treinador(
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_operacao_desportiva),
):
    query = db.query(IndisponibilidadeTreinador).filter(IndisponibilidadeTreinador.data >= date.today())
    treinadores = db.query(Treinador).order_by(Treinador.nome).all()
    if utilizador.perfil.value == "treinador":
        query = query.filter(IndisponibilidadeTreinador.treinador_id == utilizador.treinador_id)
        treinadores = [utilizador.treinador] if utilizador.treinador else []
    return templates.TemplateResponse(request, "planeamento_clube/indisponibilidades_treinador.html", {
        "utilizador": utilizador,
        "indisponibilidades": query.order_by(IndisponibilidadeTreinador.data, IndisponibilidadeTreinador.hora_inicio).all(),
        "treinadores": treinadores,
        "pode_escolher_treinador": utilizador.perfil.value in {"administrador", "coordenador", "superadministrador"},
    })


@router.post("/indisponibilidades-treinador")
def criar_indisponibilidade_treinador(
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_operacao_desportiva),
    treinador_id: str = Form(""),
    data_indisponibilidade: str = Form(...),
    hora_inicio: str = Form(...),
    hora_fim: str = Form(...),
    motivo: str = Form(""),
):
    try:
        treinador_alvo = utilizador.treinador_id if utilizador.perfil.value == "treinador" else _converter_id(treinador_id, "Treinador", obrigatorio=True)
        inicio = normalizar_hora(hora_inicio, permitir_vazio=False)
        fim = normalizar_hora(hora_fim, permitir_vazio=False)
        data_convertida = _converter_data(data_indisponibilidade, "Data")
        if not treinador_alvo or not inicio or not fim or not hora_eh_anterior(inicio, fim):
            raise ValueError("Indica um treinador, uma data e um horário válidos.")
    except ValueError as erro:
        set_flash(request, str(erro), "error")
        return RedirectResponse(url="/planeamento-clube/indisponibilidades-treinador", status_code=303)
    if not db.query(Treinador).filter(Treinador.id == treinador_alvo).first():
        set_flash(request, "O treinador indicado não pertence a este clube.", "error")
        return RedirectResponse(url="/planeamento-clube/indisponibilidades-treinador", status_code=303)
    item = IndisponibilidadeTreinador(
        treinador_id=treinador_alvo, data=data_convertida,
        hora_inicio=inicio, hora_fim=fim, motivo=motivo or None,
    )
    db.add(item)
    db.flush()
    registar_auditoria(db, utilizador, "criar", "indisponibilidade_treinador", item.id, motivo, request)
    db.commit()
    set_flash(request, "Indisponibilidade registada. O plano oficial não foi alterado.")
    return RedirectResponse(url="/planeamento-clube/indisponibilidades-treinador", status_code=303)


@router.post("/indisponibilidades-treinador/{item_id}/eliminar")
def eliminar_indisponibilidade_treinador(
    item_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_operacao_desportiva),
):
    item = db.query(IndisponibilidadeTreinador).filter(IndisponibilidadeTreinador.id == item_id).first()
    if not item:
        return RedirectResponse(url="/planeamento-clube/indisponibilidades-treinador", status_code=303)
    if utilizador.perfil.value == "treinador" and item.treinador_id != utilizador.treinador_id:
        return Response(status_code=403)
    registar_auditoria(db, utilizador, "eliminar", "indisponibilidade_treinador", item.id, item.motivo, request)
    db.delete(item)
    db.commit()
    return RedirectResponse(url="/planeamento-clube/indisponibilidades-treinador", status_code=303)


@router.get("/eventos", response_class=HTMLResponse)
def listar_eventos(request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_coordenacao)):

    return templates.TemplateResponse(request, "planeamento_clube/eventos_lista.html", {
        "utilizador": utilizador,
        "eventos": _listar_eventos_ordenados(db),
        "metadados_tipo_agenda": metadados_tipo_agenda,
    })


def _sessao_tem_exercicios_planeados(sessao: SessaoTreino) -> bool:
    """Só preservamos uma sessão quando a ficha contém exercícios reais."""
    plano = sessao.plano_treino
    return bool(plano and plano.exercicios)


def _remover_sessoes_do_plano_semanal(
    db: Session,
    semanal_id: int,
    *,
    preservar_sessoes_com_exercicios: bool,
) -> tuple[int, int]:
    """Retira da operação todas as sessões ligadas a um plano semanal."""
    removidas = preservadas = 0
    equipas_afetadas: set[int] = set()
    sessoes = db.query(SessaoTreino).filter(
        SessaoTreino.plano_semanal_clube_id == semanal_id,
    ).all()
    for sessao in sessoes:
        equipa_id = _obter_equipa_id_por_sessao(sessao)
        if equipa_id:
            equipas_afetadas.add(equipa_id)
        sessao.plano_semanal_clube_id = None
        sessao.evento_planeamento_clube_id = None
        sessao.sincronizada = False
        if preservar_sessoes_com_exercicios and _sessao_tem_exercicios_planeados(sessao):
            sessao.alterada_manual = True
            sessao.origem = "manual"
            preservadas += 1
        else:
            sessao.ativa = False
            removidas += 1
    for equipa_id in equipas_afetadas:
        renumerar_treinos_equipa(db, equipa_id)
    return removidas, preservadas


def _eliminar_evento_com_dependencias(
    db: Session,
    evento: EventoPlaneamentoClube,
    *,
    preservar_sessoes_com_exercicios: bool = False,
) -> tuple[int, int]:
    """Remove o evento e oculta todas as sessões que nasceram dessa marcação."""
    sessoes_geradas = db.query(SessaoTreino).filter(
        SessaoTreino.evento_planeamento_clube_id == evento.id,
    ).all()
    equipas_afetadas: set[int] = set()
    removidas = preservadas = 0
    for sessao in sessoes_geradas:
        preservar = preservar_sessoes_com_exercicios and _sessao_tem_exercicios_planeados(sessao)
        if preservar:
            sessao.alterada_manual = True
            sessao.origem = "manual"
            preservadas += 1
        else:
            sessao.ativa = False
            removidas += 1
        sessao.sincronizada = False
        sessao.evento_planeamento_clube_id = None
        sessao.plano_semanal_clube_id = None
        equipa_id = _obter_equipa_id_por_sessao(sessao)
        if equipa_id:
            equipas_afetadas.add(equipa_id)
    for atribuicao in evento.atribuicoes_espaco:
        atribuicao.evento_id = None
        if atribuicao.origem == OrigemAtribuicaoEspacoEnum.evento_global:
            atribuicao.origem = OrigemAtribuicaoEspacoEnum.manual
    db.delete(evento)
    for equipa_id in equipas_afetadas:
        renumerar_treinos_equipa(db, equipa_id)
    return removidas, preservadas


def _notificar_cancelamento_atribuicao(db: Session, atribuicao: AtribuicaoEspacoSemanal) -> int:
    """Avisa a equipa apenas quando a marcação já lhe tinha sido publicada."""
    if (
        atribuicao.estado != EstadoAtribuicaoEspacoEnum.publicado
        or not atribuicao.equipa
        or atribuicao.tipo_ocupacao not in {
            TipoOcupacaoEspacoEnum.treino_equipa,
            TipoOcupacaoEspacoEnum.treino_fisico,
            TipoOcupacaoEspacoEnum.treino_individual,
        }
    ):
        return 0
    return criar_notificacoes_para_equipa(
        db,
        atribuicao.equipa,
        "Treino físico cancelado" if atribuicao.tipo_ocupacao == TipoOcupacaoEspacoEnum.treino_fisico else "Treino cancelado",
        (
            f"Foi anulada a marcação de treino de {atribuicao.data.strftime('%d/%m/%Y')} "
            f"das {atribuicao.hora_inicio} às {atribuicao.hora_fim} em {atribuicao.espaco.nome}."
        ),
        f"/calendario?equipa_id={atribuicao.equipa_id}",
    )


def _notificar_cancelamento_plano_semanal(
    db: Session,
    semanal: PlanoSemanalClube,
    atribuicoes: list[AtribuicaoEspacoSemanal],
) -> int:
    """Agrupa o aviso de eliminação para não inundar cada treinador."""
    por_equipa: dict[int, list[AtribuicaoEspacoSemanal]] = {}
    for atribuicao in atribuicoes:
        if (
            atribuicao.estado == EstadoAtribuicaoEspacoEnum.publicado
            and atribuicao.equipa
            and atribuicao.tipo_ocupacao in {
                TipoOcupacaoEspacoEnum.treino_equipa,
                TipoOcupacaoEspacoEnum.treino_fisico,
                TipoOcupacaoEspacoEnum.treino_individual,
            }
        ):
            por_equipa.setdefault(atribuicao.equipa_id, []).append(atribuicao)

    total = 0
    for marcacoes in por_equipa.values():
        equipa = marcacoes[0].equipa
        quantidade = len(marcacoes)
        total += criar_notificacoes_para_equipa(
            db,
            equipa,
            "Plano semanal eliminado",
            (
                f"O plano semanal \"{semanal.titulo}\" foi eliminado. "
                f"Foram anulada(s) {quantidade} marcação(ões) de treino da equipa."
            ),
            f"/calendario?equipa_id={equipa.id}",
        )
    return total


@router.post("/eventos/eliminar-selecionados")
async def eliminar_eventos_selecionados(
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_coordenacao),
):
    form = await request.form()
    ids = sorted({int(valor) for valor in form.getlist("evento_ids") if str(valor).isdigit()})
    eventos = db.query(EventoPlaneamentoClube).filter(EventoPlaneamentoClube.id.in_(ids)).all() if ids else []
    if not eventos or str(len(eventos)) != str(form.get("confirmar_total", "")):
        set_flash(request, "A confirmação não corresponde ao número de eventos selecionados.", "error")
        return RedirectResponse(url="/planeamento-clube/eventos", status_code=303)
    for evento in eventos:
        _eliminar_evento_com_dependencias(db, evento)
    db.commit()
    set_flash(request, f"{len(eventos)} evento(s) eliminado(s).")
    return RedirectResponse(url="/planeamento-clube/eventos", status_code=303)


@router.get("/eventos/novo", response_class=HTMLResponse)
def form_novo_evento(request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_coordenacao)):

    contexto = _obter_contexto_form_evento(db)
    contexto.update({
        "utilizador": utilizador,
        "evento": None,
        "modo": "criar",
        "prefill": {
            "data": request.query_params.get("data", ""),
            "planeamento_anual_id": request.query_params.get("planeamento_anual_id", ""),
            "planeamento_mensal_id": request.query_params.get("planeamento_mensal_id", ""),
            "plano_semanal_id": request.query_params.get("plano_semanal_id", ""),
        },
    })
    return templates.TemplateResponse(request, "planeamento_clube/eventos_form.html", contexto)


@router.post("/eventos/novo")
async def criar_evento(
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_coordenacao),
    tipo: str = Form(...),
    titulo: str = Form(...),
    descricao: str = Form(""),
    data_evento: str = Form(...),
    hora_inicio: str = Form(""),
    hora_fim: str = Form(""),
    planeamento_anual_id: str = Form(""),
    planeamento_mensal_id: str = Form(""),
    plano_semanal_id: str = Form(""),
    equipa_id: str = Form(""),
    equipas_ids: list[str] = Form([]),
    espaco_id: str = Form(""),
    treinador_id: str = Form(""),
    aplica_a_todas_equipas: str = Form("false"),
    observacoes: str = Form(""),
):

    try:
        evento = _criar_evento_manual(
            tipo,
            titulo,
            descricao,
            data_evento,
            hora_inicio,
            hora_fim,
            planeamento_anual_id,
            planeamento_mensal_id,
            plano_semanal_id,
            equipa_id,
            espaco_id,
            treinador_id,
            aplica_a_todas_equipas,
            observacoes,
        )
    except ValueError as erro:
        set_flash(request, str(erro), "error")
        return RedirectResponse(url="/planeamento-clube/eventos/novo", status_code=303)
    _sincronizar_equipas_evento(db, evento, equipas_ids)
    db.add(evento)
    db.flush()
    conflitos = _conflitos_evento(db, evento)
    if conflitos:
        db.rollback()
        set_flash(request, "Conflito de agenda com: " + "; ".join(conflitos[:3]), "error")
        return RedirectResponse(url="/planeamento-clube/eventos/novo", status_code=303)
    db.commit()
    db.refresh(evento)

    return RedirectResponse(url=f"/planeamento-clube/eventos/{evento.id}", status_code=303)


@router.post("/eventos/jogo/{jogo_id}")
async def adicionar_jogo_ao_planeamento(
    jogo_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_coordenacao),
    planeamento_anual_id: str = Form(""),
    planeamento_mensal_id: str = Form(""),
    plano_semanal_id: str = Form(""),
    espaco_id: str = Form(""),
    equipas_ids: list[str] = Form([]),
    aplica_a_todas_equipas: str = Form("false"),
    observacoes: str = Form(""),
):

    jogo = db.query(Jogo).filter(Jogo.id == jogo_id).first()
    if not jogo:
        return RedirectResponse(url="/planeamento-clube/eventos")

    try:
        anual_id_convertido = _converter_id(planeamento_anual_id, "Planeamento anual")
        mensal_id_convertido = _converter_id(planeamento_mensal_id, "Planeamento mensal")
        semanal_id_convertido = _converter_id(plano_semanal_id, "Plano semanal")
        espaco_id_convertido = _converter_id(espaco_id, "Espaço")
    except ValueError as erro:
        set_flash(request, str(erro), "error")
        return RedirectResponse(url="/planeamento-clube/eventos", status_code=303)

    evento = EventoPlaneamentoClube(
        tipo=TipoEventoPlaneamentoClubeEnum.jogo,
        titulo=_obter_titulo_jogo(jogo),
        descricao=jogo.competicao or None,
        data=jogo.data,
        hora_inicio=normalizar_hora(jogo.hora),
        hora_fim=None,
        planeamento_anual_id=anual_id_convertido,
        planeamento_mensal_id=mensal_id_convertido,
        plano_semanal_id=semanal_id_convertido,
        equipa_id=jogo.equipa_id,
        espaco_id=espaco_id_convertido,
        treinador_id=None,
        jogo_id=jogo.id,
        aplica_a_todas_equipas=aplica_a_todas_equipas == "true",
        origem=OrigemEventoPlaneamentoClubeEnum.jogo_existente,
        observacoes=observacoes or jogo.observacoes or None,
    )
    _sincronizar_equipas_evento(db, evento, equipas_ids or ([str(jogo.equipa_id)] if jogo.equipa_id and aplica_a_todas_equipas != "true" else []))
    db.add(evento)
    db.commit()
    db.refresh(evento)

    return RedirectResponse(url=f"/planeamento-clube/eventos/{evento.id}", status_code=303)


@router.post("/eventos/atividade/{atividade_id}")
async def adicionar_atividade_ao_planeamento(
    atividade_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_coordenacao),
    planeamento_anual_id: str = Form(""),
    planeamento_mensal_id: str = Form(""),
    plano_semanal_id: str = Form(""),
    espaco_id: str = Form(""),
    equipas_ids: list[str] = Form([]),
    aplica_a_todas_equipas: str = Form("false"),
    observacoes: str = Form(""),
):

    atividade = db.query(Atividade).filter(Atividade.id == atividade_id).first()
    if not atividade:
        return RedirectResponse(url="/planeamento-clube/eventos")

    try:
        anual_id_convertido = _converter_id(planeamento_anual_id, "Planeamento anual")
        mensal_id_convertido = _converter_id(planeamento_mensal_id, "Planeamento mensal")
        semanal_id_convertido = _converter_id(plano_semanal_id, "Plano semanal")
        espaco_id_convertido = _converter_id(espaco_id, "Espaço")
    except ValueError as erro:
        set_flash(request, str(erro), "error")
        return RedirectResponse(url="/planeamento-clube/eventos", status_code=303)

    evento = EventoPlaneamentoClube(
        tipo=TipoEventoPlaneamentoClubeEnum.atividade_extra,
        titulo=atividade.titulo,
        descricao=atividade.descricao or atividade.tipo or None,
        data=atividade.data,
        hora_inicio=None,
        hora_fim=None,
        planeamento_anual_id=anual_id_convertido,
        planeamento_mensal_id=mensal_id_convertido,
        plano_semanal_id=semanal_id_convertido,
        equipa_id=None,
        espaco_id=espaco_id_convertido,
        treinador_id=None,
        atividade_id=atividade.id,
        aplica_a_todas_equipas=aplica_a_todas_equipas == "true",
        origem=OrigemEventoPlaneamentoClubeEnum.atividade_existente,
        observacoes=observacoes or atividade.observacoes or None,
    )
    _sincronizar_equipas_evento(db, evento, equipas_ids)
    db.add(evento)
    db.commit()
    db.refresh(evento)

    return RedirectResponse(url=f"/planeamento-clube/eventos/{evento.id}", status_code=303)


@router.get("/eventos/{evento_id}", response_class=HTMLResponse)
def detalhe_evento(evento_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_coordenacao)):

    evento = db.query(EventoPlaneamentoClube).filter(EventoPlaneamentoClube.id == evento_id).first()
    if not evento:
        return RedirectResponse(url="/planeamento-clube/eventos")

    return templates.TemplateResponse(request, "planeamento_clube/evento_detalhe.html", {
        "utilizador": utilizador,
        "evento": evento,
        "metadados_tipo_agenda": metadados_tipo_agenda,
    })


@router.get("/eventos/{evento_id}/editar", response_class=HTMLResponse)
def form_editar_evento(evento_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_coordenacao)):

    evento = db.query(EventoPlaneamentoClube).filter(EventoPlaneamentoClube.id == evento_id).first()
    if not evento:
        return RedirectResponse(url="/planeamento-clube/eventos")

    contexto = _obter_contexto_form_evento(db)
    contexto.update({
        "utilizador": utilizador,
        "evento": evento,
        "modo": "editar",
    })
    return templates.TemplateResponse(request, "planeamento_clube/eventos_form.html", contexto)


@router.post("/eventos/{evento_id}/editar")
async def editar_evento(
    evento_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_coordenacao),
    tipo: str = Form(...),
    titulo: str = Form(...),
    descricao: str = Form(""),
    data_evento: str = Form(...),
    hora_inicio: str = Form(""),
    hora_fim: str = Form(""),
    planeamento_anual_id: str = Form(""),
    planeamento_mensal_id: str = Form(""),
    plano_semanal_id: str = Form(""),
    equipa_id: str = Form(""),
    equipas_ids: list[str] = Form([]),
    espaco_id: str = Form(""),
    treinador_id: str = Form(""),
    aplica_a_todas_equipas: str = Form("false"),
    observacoes: str = Form(""),
):

    evento = db.query(EventoPlaneamentoClube).filter(EventoPlaneamentoClube.id == evento_id).first()
    if not evento:
        return RedirectResponse(url="/planeamento-clube/eventos")

    try:
        _atualizar_evento(
            evento,
            tipo,
            titulo,
            descricao,
            data_evento,
            hora_inicio,
            hora_fim,
            planeamento_anual_id,
            planeamento_mensal_id,
            plano_semanal_id,
            equipa_id,
            espaco_id,
            treinador_id,
            aplica_a_todas_equipas,
            observacoes,
        )
    except ValueError as erro:
        set_flash(request, str(erro), "error")
        return RedirectResponse(url=f"/planeamento-clube/eventos/{evento.id}/editar", status_code=303)
    _sincronizar_equipas_evento(db, evento, equipas_ids)
    conflitos = _conflitos_evento(db, evento)
    if conflitos:
        db.rollback()
        set_flash(request, "Conflito de agenda com: " + "; ".join(conflitos[:3]), "error")
        return RedirectResponse(url=f"/planeamento-clube/eventos/{evento.id}/editar", status_code=303)
    db.commit()

    return RedirectResponse(url=f"/planeamento-clube/eventos/{evento.id}", status_code=303)


@router.post("/eventos/{evento_id}/eliminar")
async def eliminar_evento(evento_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_coordenacao)):

    evento = db.query(EventoPlaneamentoClube).filter(EventoPlaneamentoClube.id == evento_id).first()
    if evento:
        _eliminar_evento_com_dependencias(db, evento)
        db.commit()

    return RedirectResponse(url="/planeamento-clube/eventos", status_code=303)

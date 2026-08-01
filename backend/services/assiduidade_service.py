"""Regras comuns para registo e análise de assiduidade."""

from collections import Counter
from datetime import date

from sqlalchemy.orm import Session

from models.assiduidade import RegistoAssiduidade
from models.jogador import Jogador
from models.planeamento import Macrociclo, Mesociclo, Microciclo, SessaoTreino


ESTADOS_ASSIDUIDADE = (
    "por_registar",
    "presente",
    "atrasada",
    "ausente",
    "justificada",
    "lesionada",
    "dispensada",
)
ESTADOS_ASSIDUIDADE_VISUAL = {
    "por_registar": {"label": "Por registar", "classes": "bg-slate-100 text-slate-600"},
    "presente": {"label": "Presente", "classes": "bg-green-100 text-green-700"},
    "atrasada": {"label": "Atrasada", "classes": "bg-amber-100 text-amber-700"},
    "ausente": {"label": "Ausente", "classes": "bg-red-100 text-red-700"},
    "justificada": {"label": "Falta justificada", "classes": "bg-blue-100 text-blue-700"},
    "lesionada": {"label": "Lesionada", "classes": "bg-purple-100 text-purple-700"},
    "dispensada": {"label": "Dispensada", "classes": "bg-gray-200 text-gray-700"},
}
ESTADOS_PRESENTES = {"presente", "atrasada"}


def normalizar_estado_assiduidade(estado: str | None, presente: bool = False) -> str:
    """Normaliza formulários e converte registos antigos que só tinham booleano."""
    valor = (estado or "").strip().lower()
    if valor in ESTADOS_ASSIDUIDADE:
        return valor
    return "presente" if presente else "ausente"


def estado_assiduidade_visual(estado: str | None, presente: bool = False) -> dict:
    codigo = normalizar_estado_assiduidade(estado, presente)
    return {"codigo": codigo, **ESTADOS_ASSIDUIDADE_VISUAL[codigo]}


def estado_para_presenca(estado: str | None, presente: bool = False) -> bool:
    return normalizar_estado_assiduidade(estado, presente) in ESTADOS_PRESENTES


def calcular_resumo_assiduidade(registos: list[RegistoAssiduidade]) -> dict:
    estados = [
        normalizar_estado_assiduidade(getattr(registo, "estado", None), registo.presente)
        for registo in registos
    ]
    contagem = Counter(estados)
    total = len(estados)
    total_presentes = sum(contagem[estado] for estado in ESTADOS_PRESENTES)
    return {
        "total": total,
        "presentes": total_presentes,
        "percentagem": round((total_presentes / total) * 100, 1) if total else 0,
        "por_estado": {estado: contagem[estado] for estado in ESTADOS_ASSIDUIDADE},
    }


def _sessoes_da_equipa(
    db: Session,
    equipa_id: int,
    data_inicio: date | None = None,
    data_fim: date | None = None,
) -> list[SessaoTreino]:
    consulta = (
        db.query(SessaoTreino)
        .join(Microciclo, SessaoTreino.microciclo_id == Microciclo.id)
        .join(Mesociclo, Microciclo.mesociclo_id == Mesociclo.id)
        .join(Macrociclo, Mesociclo.macrociclo_id == Macrociclo.id)
        .filter(Macrociclo.equipa_id == equipa_id, SessaoTreino.ativa.is_(True))
        .order_by(SessaoTreino.data.desc(), SessaoTreino.id.desc())
    )
    if data_inicio:
        consulta = consulta.filter(SessaoTreino.data >= data_inicio)
    if data_fim:
        consulta = consulta.filter(SessaoTreino.data <= data_fim)
    return consulta.all()


def obter_relatorio_assiduidade_equipa(
    db: Session,
    equipa_id: int,
    data_inicio: date | None = None,
    data_fim: date | None = None,
) -> dict:
    """Calcula o relatório sem assumir faltas para registos inexistentes."""
    sessoes = _sessoes_da_equipa(db, equipa_id, data_inicio, data_fim)
    sessao_ids = [sessao.id for sessao in sessoes]
    jogadores = db.query(Jogador).filter(Jogador.equipa_id == equipa_id).order_by(Jogador.nome).all()
    registos = (
        db.query(RegistoAssiduidade)
        .filter(RegistoAssiduidade.sessao_id.in_(sessao_ids))
        .all()
        if sessao_ids else []
    )
    por_jogador: dict[int, list[RegistoAssiduidade]] = {jogador.id: [] for jogador in jogadores}
    for registo in registos:
        if registo.jogador_id in por_jogador:
            por_jogador[registo.jogador_id].append(registo)

    linhas = []
    for jogador in jogadores:
        resumo = calcular_resumo_assiduidade(por_jogador[jogador.id])
        linhas.append({"jogador": jogador, **resumo})

    return {
        "linhas": linhas,
        "sessoes": sessoes,
        "sessoes_total": len(sessoes),
        "sessoes_com_registo": len({registo.sessao_id for registo in registos}),
        "resumo": calcular_resumo_assiduidade(registos),
        "data_inicio": data_inicio,
        "data_fim": data_fim,
    }


def obter_relatorio_assiduidade_jogador(db: Session, jogador_id: int) -> dict:
    """Obtém o resumo individual e os últimos registos do jogador."""
    registos = (
        db.query(RegistoAssiduidade)
        .join(SessaoTreino, RegistoAssiduidade.sessao_id == SessaoTreino.id)
        .join(Microciclo, SessaoTreino.microciclo_id == Microciclo.id)
        .join(Mesociclo, Microciclo.mesociclo_id == Mesociclo.id)
        .join(Macrociclo, Mesociclo.macrociclo_id == Macrociclo.id)
        .filter(RegistoAssiduidade.jogador_id == jogador_id, SessaoTreino.ativa.is_(True))
        .order_by(SessaoTreino.data.desc(), RegistoAssiduidade.id.desc())
        .all()
    )
    for registo in registos:
        registo.estado_visual = estado_assiduidade_visual(registo.estado, registo.presente)
    return {"registos": registos, **calcular_resumo_assiduidade(registos)}

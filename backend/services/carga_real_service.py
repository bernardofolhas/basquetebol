"""Análise comum da intensidade e da carga reais dos treinos."""

from collections import defaultdict
from datetime import date

from sqlalchemy.orm import Session

from models.assiduidade import RegistoAssiduidade
from models.planeamento import SessaoTreino


def _media(valores: list[float]) -> float | None:
    return round(sum(valores) / len(valores), 1) if valores else None


def analisar_carga_sessoes(db: Session, sessoes: list[SessaoTreino]) -> dict:
    """Compara carga planeada e carga real a partir da RPE individual."""
    treinos = sorted(
        [sessao for sessao in sessoes if sessao.ativa and not sessao.e_jogo],
        key=lambda sessao: (sessao.data, sessao.hora_inicio or "", sessao.id or 0),
    )
    ids = [sessao.id for sessao in treinos if sessao.id]
    registos = (
        db.query(RegistoAssiduidade)
        .filter(
            RegistoAssiduidade.sessao_id.in_(ids),
            RegistoAssiduidade.rpe_individual.isnot(None),
        )
        .all()
        if ids else []
    )
    rpes_por_sessao: dict[int, list[float]] = defaultdict(list)
    for registo in registos:
        rpes_por_sessao[registo.sessao_id].append(float(registo.rpe_individual))

    linhas = []
    todas_rpes = []
    carga_real_total = 0.0
    carga_planeada_comparavel = 0.0
    sessoes_comparaveis = 0
    for sessao in treinos:
        respostas = rpes_por_sessao.get(sessao.id, [])
        rpe_real = _media(respostas)
        volume = sessao.volume_minutos or 0
        carga_planeada = (
            round(volume * float(sessao.intensidade_rpe), 1)
            if sessao.intensidade_rpe is not None else None
        )
        carga_real = round(volume * rpe_real, 1) if rpe_real is not None else None
        if carga_real is not None:
            carga_real_total += carga_real
            if carga_planeada is not None:
                carga_planeada_comparavel += carga_planeada
                sessoes_comparaveis += 1
        todas_rpes.extend(respostas)
        linhas.append({
            "sessao": sessao,
            "volume": volume,
            "rpe_planeada": sessao.intensidade_rpe,
            "rpe_real": rpe_real,
            "respostas": len(respostas),
            "carga_planeada": carga_planeada,
            "carga_real": carga_real,
        })

    sessoes_com_rpe = sum(1 for linha in linhas if linha["rpe_real"] is not None)
    sessoes_analisaveis = sum(
        1 for linha in linhas
        if linha["rpe_real"] is not None
        or linha["sessao"].data <= date.today()
        or (linha["sessao"].estado or "").lower() in {"executada", "realizada", "concluida"}
    )
    desvio = (
        round(carga_real_total - carga_planeada_comparavel, 1)
        if sessoes_comparaveis else None
    )
    return {
        "linhas": linhas,
        "por_sessao": {linha["sessao"].id: linha for linha in linhas},
        "intensidade_real": _media(todas_rpes),
        "respostas": len(todas_rpes),
        "sessoes_total": sessoes_analisaveis,
        "sessoes_com_rpe": sessoes_com_rpe,
        "cobertura": round(sessoes_com_rpe * 100 / sessoes_analisaveis) if sessoes_analisaveis else 0,
        "carga_real": round(carga_real_total, 1) if sessoes_com_rpe else None,
        "carga_planeada_comparavel": (
            round(carga_planeada_comparavel, 1) if sessoes_comparaveis else None
        ),
        "desvio_carga": desvio,
    }


def analisar_carga_jogador(db: Session, jogador_id: int) -> dict:
    """Calcula a carga individual usando apenas a RPE comunicada pelo atleta."""
    registos = (
        db.query(RegistoAssiduidade)
        .join(SessaoTreino, RegistoAssiduidade.sessao_id == SessaoTreino.id)
        .filter(
            RegistoAssiduidade.jogador_id == jogador_id,
            RegistoAssiduidade.rpe_individual.isnot(None),
            SessaoTreino.ativa.is_(True),
            SessaoTreino.e_jogo.is_(False),
        )
        .order_by(SessaoTreino.data.desc(), SessaoTreino.hora_inicio.desc(), RegistoAssiduidade.id.desc())
        .all()
    )
    linhas = []
    for registo in registos:
        volume = registo.sessao.volume_minutos or 0
        rpe = float(registo.rpe_individual)
        linhas.append({
            "sessao": registo.sessao,
            "rpe": rpe,
            "volume": volume,
            "carga": round(volume * rpe, 1),
        })
    return {
        "intensidade_media": _media([linha["rpe"] for linha in linhas]),
        "carga_total": round(sum(linha["carga"] for linha in linhas), 1) if linhas else None,
        "respostas": len(linhas),
        "ultima_rpe": linhas[0]["rpe"] if linhas else None,
        "historico": linhas[:12],
    }

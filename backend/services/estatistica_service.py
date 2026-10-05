import json
from collections import defaultdict

from models.estatistica import EventoEstatistica


TIPOS_EVENTO = {
    "ll_c", "ll_f", "dois_c", "dois_f", "tres_c", "tres_f",
    "ressalto_ofensivo", "ressalto_defensivo", "assistencia", "roubo",
    "perda", "desarme", "falta", "falta_sofrida", "entrada_campo", "saida_campo",
}
TIPOS_ALINHAMENTO = {"entrada_campo", "saida_campo"}
PONTOS_POR_TIPO = {"ll_c": 1, "dois_c": 2, "tres_c": 3}


def pontos_eventos(eventos: list[EventoEstatistica], lado: str) -> int:
    return sum(
        PONTOS_POR_TIPO.get(evento.tipo, 0)
        for evento in eventos
        if evento.lado == lado and not evento.anulado
    )


def segundos_jogados_eventos(
    eventos: list[EventoEstatistica],
    periodo_atual: int | None = None,
    segundos_restantes: int | None = None,
) -> dict[int, int]:
    """Calcula o tempo a partir das entradas e saídas registadas no relógio decrescente."""
    por_periodo: dict[int, list[EventoEstatistica]] = defaultdict(list)
    for evento in eventos:
        if (
            not evento.anulado
            and evento.lado == "equipa"
            and evento.jogador_id
            and evento.tipo in TIPOS_ALINHAMENTO
        ):
            por_periodo[evento.periodo].append(evento)

    totais: dict[int, int] = defaultdict(int)
    for periodo, registos in por_periodo.items():
        entradas: dict[int, int] = {}
        registos.sort(key=lambda item: (-(item.segundos_restantes or 0), item.id or 0))
        for evento in registos:
            relogio = max(0, evento.segundos_restantes or 0)
            if evento.tipo == "entrada_campo":
                entradas.setdefault(evento.jogador_id, relogio)
            elif evento.jogador_id in entradas:
                totais[evento.jogador_id] += max(0, entradas.pop(evento.jogador_id) - relogio)
        for jogador_id, entrada in entradas.items():
            if periodo_atual is not None and periodo < periodo_atual:
                totais[jogador_id] += entrada
            elif periodo_atual == periodo and segundos_restantes is not None:
                totais[jogador_id] += max(0, entrada - segundos_restantes)
    oficiais = {
        evento.jogador_id: evento.segundos_jogados_oficiais
        for evento in eventos
        if not evento.anulado
        and evento.lado == "equipa"
        and evento.jogador_id
        and getattr(evento, "segundos_jogados_oficiais", None) is not None
    }
    totais.update(oficiais)
    return dict(totais)


def box_score_eventos(
    eventos: list[EventoEstatistica],
    periodo_atual: int | None = None,
    segundos_restantes: int | None = None,
) -> dict[int, dict]:
    tempos = segundos_jogados_eventos(eventos, periodo_atual, segundos_restantes)
    linhas = defaultdict(lambda: {
        "pts": 0, "ll_c": 0, "ll_t": 0, "dois_c": 0, "dois_t": 0,
        "tres_c": 0, "tres_t": 0, "ro": 0, "rd": 0, "ast": 0,
        "stl": 0, "to": 0, "blk": 0, "pf": 0, "eff": 0, "segundos_jogados": 0,
    })
    for evento in eventos:
        if evento.anulado or evento.lado != "equipa" or not evento.jogador_id:
            continue
        linha = linhas[evento.jogador_id]
        tipo = evento.tipo
        linha["pts"] += PONTOS_POR_TIPO.get(tipo, 0)
        if tipo.startswith("ll_"):
            linha["ll_t"] += 1
            linha["ll_c"] += int(tipo == "ll_c")
        elif tipo.startswith("dois_"):
            linha["dois_t"] += 1
            linha["dois_c"] += int(tipo == "dois_c")
        elif tipo.startswith("tres_"):
            linha["tres_t"] += 1
            linha["tres_c"] += int(tipo == "tres_c")
        elif tipo == "ressalto_ofensivo": linha["ro"] += 1
        elif tipo == "ressalto_defensivo": linha["rd"] += 1
        elif tipo == "assistencia": linha["ast"] += 1
        elif tipo == "roubo": linha["stl"] += 1
        elif tipo == "perda": linha["to"] += 1
        elif tipo == "desarme": linha["blk"] += 1
        elif tipo == "falta": linha["pf"] += 1
    for linha in linhas.values():
        falhados = (linha["ll_t"] - linha["ll_c"]) + (linha["dois_t"] - linha["dois_c"]) + (linha["tres_t"] - linha["tres_c"])
        linha["eff"] = linha["pts"] + linha["ro"] + linha["rd"] + linha["ast"] + linha["stl"] + linha["blk"] - falhados - linha["to"]
    for jogador_id, total in tempos.items():
        linhas[jogador_id]["segundos_jogados"] = total
    return dict(linhas)


def serializar_evento(evento: EventoEstatistica) -> dict:
    return {
        "id": evento.id,
        "client_uid": evento.client_uid,
        "jogador_id": evento.jogador_id,
        "jogador": evento.jogador.nome if evento.jogador else evento.jogador_externo,
        "lado": evento.lado,
        "tipo": evento.tipo,
        "periodo": evento.periodo,
        "segundos_restantes": evento.segundos_restantes,
        "posicao_x": evento.posicao_x,
        "posicao_y": evento.posicao_y,
        "origem": evento.origem,
        "subtipo": evento.subtipo,
        "qualificadores": json.loads(evento.qualificadores or "[]"),
        "anulado": evento.anulado,
        "sincronizado": True,
        "segundos_jogados_oficiais": evento.segundos_jogados_oficiais,
    }

from collections import defaultdict

from models.estatistica import EventoEstatistica


TIPOS_EVENTO = {
    "ll_c", "ll_f", "dois_c", "dois_f", "tres_c", "tres_f",
    "ressalto_ofensivo", "ressalto_defensivo", "assistencia", "roubo",
    "perda", "desarme", "falta", "falta_sofrida",
}
PONTOS_POR_TIPO = {"ll_c": 1, "dois_c": 2, "tres_c": 3}


def pontos_eventos(eventos: list[EventoEstatistica], lado: str) -> int:
    return sum(
        PONTOS_POR_TIPO.get(evento.tipo, 0)
        for evento in eventos
        if evento.lado == lado and not evento.anulado
    )


def box_score_eventos(eventos: list[EventoEstatistica]) -> dict[int, dict]:
    linhas = defaultdict(lambda: {
        "pts": 0, "ll_c": 0, "ll_t": 0, "dois_c": 0, "dois_t": 0,
        "tres_c": 0, "tres_t": 0, "ro": 0, "rd": 0, "ast": 0,
        "stl": 0, "to": 0, "blk": 0, "pf": 0, "eff": 0,
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
    return dict(linhas)


def serializar_evento(evento: EventoEstatistica) -> dict:
    return {
        "id": evento.id,
        "client_uid": evento.client_uid,
        "jogador_id": evento.jogador_id,
        "jogador": evento.jogador.nome if evento.jogador else None,
        "lado": evento.lado,
        "tipo": evento.tipo,
        "periodo": evento.periodo,
        "segundos_restantes": evento.segundos_restantes,
        "posicao_x": evento.posicao_x,
        "posicao_y": evento.posicao_y,
        "anulado": evento.anulado,
        "sincronizado": True,
    }

import random
import unicodedata


POSICOES_INTERIORES = ("poste", "pivot", "pivo", "interior", "center", "centro")


def normalizar_texto(valor: str | None) -> str:
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    return "".join(caracter for caracter in texto if not unicodedata.combining(caracter)).casefold()


def jogador_e_interior(posicao: str | None) -> bool:
    posicao_normalizada = normalizar_texto(posicao)
    return any(termo in posicao_normalizada for termo in POSICOES_INTERIORES)


def gerar_equipas_equilibradas(
    jogadores: list[dict],
    tamanho_base: int,
    postes_por_equipa: int | None = None,
    gerador: random.Random | None = None,
) -> dict:
    """Distribui todos os atletas e reserva interiores/mais altos por equipa."""
    if tamanho_base not in {2, 3, 4, 5}:
        raise ValueError("O tamanho das equipas deve estar entre 2 e 5.")
    if not jogadores:
        raise ValueError("Seleciona pelo menos um atleta previsto.")

    if tamanho_base == 4:
        postes_necessarios = 2 if postes_por_equipa == 2 else 1
    elif tamanho_base in {3, 5}:
        postes_necessarios = 1
    else:
        postes_necessarios = 0

    sorteio = gerador or random.SystemRandom()
    total_equipas = max(1, len(jogadores) // tamanho_base)
    tamanho_equilibrado, resto = divmod(len(jogadores), total_equipas)
    tamanhos = [
        tamanho_equilibrado + (1 if indice >= total_equipas - resto else 0)
        for indice in range(total_equipas)
    ]

    candidatos = list(jogadores)
    sorteio.shuffle(candidatos)
    candidatos.sort(key=lambda item: (
        0 if item.get("interior") else 1,
        -(float(item["altura"]) if item.get("altura") is not None else -1),
    ))
    quantidade_grandes = min(len(jogadores), total_equipas * postes_necessarios)
    grandes = candidatos[:quantidade_grandes]
    grandes_ids = {int(item["id"]) for item in grandes}

    equipas = [[] for _ in range(total_equipas)]
    for ronda in range(postes_necessarios):
        for indice in range(total_equipas):
            posicao = ronda * total_equipas + indice
            if posicao >= len(grandes) or len(equipas[indice]) >= tamanhos[indice]:
                continue
            equipas[indice].append(int(grandes[posicao]["id"]))

    restantes = [item for item in jogadores if int(item["id"]) not in grandes_ids]
    sorteio.shuffle(restantes)
    for equipa, tamanho in zip(equipas, tamanhos):
        while len(equipa) < tamanho and restantes:
            equipa.append(int(restantes.pop()["id"]))

    return {
        "tamanho": tamanho_base,
        "postes_por_equipa": postes_necessarios,
        "grandes_ids": sorted(grandes_ids),
        "equipas": [
            {"nome": f"Equipa {indice + 1}", "slots": slots}
            for indice, slots in enumerate(equipas)
        ],
    }

import random
import unicodedata
import math


POSICOES_INTERIORES = ("poste", "pivot", "pivo", "interior", "center", "centro")


def normalizar_texto(valor: str | None) -> str:
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    return "".join(caracter for caracter in texto if not unicodedata.combining(caracter)).casefold()


def jogador_e_interior(posicao: str | None) -> bool:
    posicao_normalizada = normalizar_texto(posicao)
    return any(termo in posicao_normalizada for termo in POSICOES_INTERIORES)


def posicao_agrupamento(valor: str | None) -> str | None:
    texto = normalizar_texto(str(valor or "").split("/")[0].strip())
    if any(termo in texto for termo in POSICOES_INTERIORES):
        return "Poste"
    if "extremo" in texto or "ala" in texto:
        return "Extremo"
    if "base" in texto or "armador" in texto:
        return "Base"
    return None


def posicoes_jogador(jogador: dict) -> tuple[str | None, str | None]:
    partes = str(jogador.get("posicao") or "").split("/", 1)
    principal = posicao_agrupamento(partes[0])
    secundaria = posicao_agrupamento(jogador.get("posicao_secundaria") or (partes[1] if len(partes) > 1 else None))
    return principal, secundaria if secundaria != principal else None


def altura_jogador(jogador: dict) -> float | None:
    try:
        altura = float(jogador["altura"])
    except (TypeError, ValueError, KeyError):
        return None
    return altura if math.isfinite(altura) and altura > 0 else None


def _chave_altura(jogador: dict, papel: str, altura_mediana: float) -> tuple:
    altura = altura_jogador(jogador)
    if altura is None:
        return (1, 0)
    if papel == "Base":
        return (0, altura)
    if papel == "Poste":
        return (0, -altura)
    return (0, abs(altura - altura_mediana))


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

    if tamanho_base in {4, 5}:
        postes_necessarios = 2 if postes_por_equipa == 2 or (tamanho_base == 5 and postes_por_equipa is None) else 1
    elif tamanho_base == 3:
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
    alturas = sorted(altura for item in candidatos if (altura := altura_jogador(item)) is not None)
    altura_mediana = alturas[len(alturas) // 2] if alturas else 0
    equipas = [[] for _ in range(total_equipas)]
    posicoes_ids = {}
    necessidades = []
    for tamanho in tamanhos:
        postes = min(postes_necessarios, max(0, tamanho - 1))
        base = 1 if tamanho else 0
        necessidades.append({"Base": base, "Poste": postes, "Extremo": tamanho - base - postes})
    lugares = []
    for papel in ("Base", "Poste", "Extremo"):
        for ronda in range(max(necessidade[papel] for necessidade in necessidades)):
            lugares.extend(
                (indice, papel)
                for indice, necessidade in enumerate(necessidades)
                if necessidade[papel] > ronda
            )

    # Reserva alternativas indispensaveis antes de ocupar vagas da posicao principal.
    reservados = set()
    for papel in ("Base", "Poste", "Extremo"):
        falta = max(0, sum(necessidade[papel] for necessidade in necessidades) - sum(
            posicoes_jogador(item)[0] == papel for item in jogadores
        ))
        alternativas = [item for item in candidatos if (
            posicoes_jogador(item)[1] == papel and int(item["id"]) not in reservados
        )]
        alternativas.sort(key=lambda item: _chave_altura(item, papel, altura_mediana))
        reservados.update(int(item["id"]) for item in alternativas[:falta])

    # Primeiro esgota posições principais, depois alternativas; só então recorre à altura.
    for fase in (0, 1, 2):
        for papel in ("Base", "Poste", "Extremo"):
            for indice, lugar_papel in lugares:
                if lugar_papel != papel or sum(
                    posicoes_ids[str(id_)] == papel for id_ in equipas[indice]
                ) >= necessidades[indice][papel]:
                    continue
                disponiveis = [item for item in candidatos if (
                    altura_jogador(item) is not None and not any(posicoes_jogador(item))
                    if fase == 2 else posicoes_jogador(item)[fase] == papel
                    and (fase != 0 or int(item["id"]) not in reservados)
                )]
                if not disponiveis:
                    continue
                disponiveis.sort(key=lambda item: (
                    0 if fase == 0 and posicoes_jogador(item)[1] is None else 1,
                    _chave_altura(item, papel, altura_mediana),
                ))
                escolhido = disponiveis[0]
                id_ = int(escolhido["id"])
                equipas[indice].append(id_)
                posicoes_ids[str(id_)] = papel
                candidatos.remove(escolhido)

    # Os atletas restantes conservam o papel declarado, mesmo com altura registada.
    for escolhido in candidatos:
        indice = min(
            (indice for indice in range(total_equipas) if len(equipas[indice]) < tamanhos[indice]),
            key=lambda indice: len(equipas[indice]) / tamanhos[indice],
        )
        id_ = int(escolhido["id"])
        equipas[indice].append(id_)
        principal, secundaria = posicoes_jogador(escolhido)
        if principal or secundaria:
            posicoes_ids[str(id_)] = principal or secundaria

    grandes_ids = sorted(int(id_) for id_, papel in posicoes_ids.items() if papel == "Poste")
    ordem_papeis = {"Base": 0, "Extremo": 1, "Poste": 2}
    for equipa in equipas:
        equipa.sort(key=lambda id_: ordem_papeis.get(posicoes_ids.get(str(id_)), 3))

    return {
        "tamanho": tamanho_base,
        "postes_por_equipa": postes_necessarios,
        "grandes_ids": grandes_ids,
        "posicoes_ids": posicoes_ids,
        "equipas": [
            {"nome": f"Equipa {indice + 1}", "slots": slots}
            for indice, slots in enumerate(equipas)
        ],
    }

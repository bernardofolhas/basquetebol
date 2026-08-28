import calendar
from collections import defaultdict
from datetime import date
import re


MESES_EPOCA = (
    (8, "Agosto"),
    (9, "Setembro"),
    (10, "Outubro"),
    (11, "Novembro"),
    (12, "Dezembro"),
    (1, "Janeiro"),
    (2, "Fevereiro"),
    (3, "Março"),
    (4, "Abril"),
    (5, "Maio"),
    (6, "Junho"),
)
DIAS_SEMANA_ABREVIADOS = ("2ª", "3ª", "4ª", "5ª", "6ª", "S", "D")


def formatar_confronto(nome_clube: str | None, adversario: str | None, em_casa: bool) -> str:
    """Apresenta o confronto sempre pela perspetiva do clube anfitrião/visitante."""
    clube = (nome_clube or "Clube").strip()
    oponente = (adversario or "Adversário por definir").strip()
    return f"{clube} vs {oponente}" if em_casa else f"{oponente} vs {clube}"


def separar_visitada_visitante(
    nome_clube: str | None,
    adversario: str | None,
    em_casa: bool,
) -> tuple[str, str]:
    """Devolve as equipas pela perspetiva oficial da ficha de jogo."""
    clube = (nome_clube or "Clube").strip()
    oponente = (adversario or "Adversário por definir").strip()
    return (clube, oponente) if em_casa else (oponente, clube)


def preparar_linhas_calendario_jogos(jogos: list, nome_clube: str | None) -> list[dict]:
    """Prepara uma representação única dos jogos para os PDFs de calendário."""
    linhas = []
    for jogo in jogos:
        visitada, visitante = separar_visitada_visitante(
            nome_clube,
            jogo.adversario,
            jogo.em_casa,
        )
        linhas.append({
            "jogo": jogo,
            "visitada": visitada,
            "visitante": visitante,
        })
    return linhas


def _ano_inicio_epoca(data_jogo: date) -> int:
    return data_jogo.year if data_jogo.month >= 8 else data_jogo.year - 1


def _ano_inicio_epoca_texto(epoca: str | None) -> int | None:
    correspondencia = re.search(r"(\d{4})\D+(\d{4})", epoca or "")
    return int(correspondencia.group(1)) if correspondencia else None


def preparar_epocas_calendario_jogos(
    jogos: list,
    epoca_predefinida: str | None = None,
) -> list[dict]:
    """Constrói grelhas anuais de agosto a junho sem omitir épocas com jogos."""
    jogos_ordenados = sorted(jogos, key=lambda jogo: (jogo.data, jogo.hora or "", jogo.id or 0))
    por_epoca: dict[int, list] = defaultdict(list)
    for jogo in jogos_ordenados:
        por_epoca[_ano_inicio_epoca(jogo.data)].append(jogo)

    if not por_epoca:
        ano_inicio = _ano_inicio_epoca_texto(epoca_predefinida) or _ano_inicio_epoca(date.today())
        por_epoca[ano_inicio] = []

    epocas = []
    for ano_inicio, jogos_epoca in sorted(por_epoca.items()):
        jogos_por_data: dict[date, list[dict]] = defaultdict(list)
        for numero, jogo in enumerate(jogos_epoca, start=1):
            jogos_por_data[jogo.data].append({"numero": numero, "jogo": jogo})

        meses_config = list(MESES_EPOCA)
        if any(jogo.data.month == 7 for jogo in jogos_epoca):
            meses_config.append((7, "Julho"))

        meses = []
        for numero_mes, nome_mes in meses_config:
            ano_mes = ano_inicio if numero_mes >= 8 else ano_inicio + 1
            ultimo_dia = calendar.monthrange(ano_mes, numero_mes)[1]
            dias = []
            for numero_dia in range(1, 32):
                if numero_dia > ultimo_dia:
                    dias.append({"valido": False, "numero": numero_dia, "jogos": [], "fim_semana": False})
                    continue
                data_dia = date(ano_mes, numero_mes, numero_dia)
                dias.append({
                    "valido": True,
                    "numero": numero_dia,
                    "jogos": jogos_por_data.get(data_dia, []),
                    "fim_semana": data_dia.weekday() >= 5,
                })
            meses.append({"nome": nome_mes, "ano": ano_mes, "dias": dias})

        epocas.append({
            "ano_inicio": ano_inicio,
            "epoca": f"{ano_inicio}/{ano_inicio + 1}",
            "meses": meses,
            "jogos": jogos_epoca,
            # A coluna fixa à esquerda usa agosto como referência da semana.
            "dias_semana_referencia": [
                DIAS_SEMANA_ABREVIADOS[date(ano_inicio, 8, numero_dia).weekday()]
                for numero_dia in range(1, 32)
            ],
        })
    return epocas

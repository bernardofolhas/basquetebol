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

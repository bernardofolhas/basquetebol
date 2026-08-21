def formatar_confronto(nome_clube: str | None, adversario: str | None, em_casa: bool) -> str:
    """Apresenta o confronto sempre pela perspetiva do clube anfitrião/visitante."""
    clube = (nome_clube or "Clube").strip()
    oponente = (adversario or "Adversário por definir").strip()
    return f"{clube} vs {oponente}" if em_casa else f"{oponente} vs {clube}"

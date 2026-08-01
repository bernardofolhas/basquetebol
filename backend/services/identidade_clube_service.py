import re
from pathlib import Path

from models.identidade_clube import IdentidadeClube


CORES_PADRAO = {
    "nome_oficial": "Clube de Basquetebol",
    "nome_curto": "Basquetebol",
    "logo_principal": None,
    "logo_secundario": None,
    "cor_principal": "#f97316",
    "cor_secundaria": "#1f2937",
    "cor_destaque": "#0ea5e9",
    "texto_rodape": "Plataforma de Gestão de Basquetebol",
    "epoca_predefinida": None,
}
_COR_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def normalizar_cor(valor: str | None, fallback: str) -> str:
    valor = (valor or "").strip()
    return valor if _COR_HEX_RE.fullmatch(valor) else fallback


def _rgb(cor: str) -> tuple[int, int, int]:
    return tuple(int(cor[indice:indice + 2], 16) for indice in (1, 3, 5))


def _hex(rgb: tuple[int, int, int]) -> str:
    return "#%02x%02x%02x" % tuple(max(0, min(255, valor)) for valor in rgb)


def _misturar(cor: str, alvo: str, proporcao: float) -> str:
    origem = _rgb(cor)
    destino = _rgb(alvo)
    return _hex(tuple(round(a + (b - a) * proporcao) for a, b in zip(origem, destino)))


def _luminancia(cor: str) -> float:
    canais = []
    for canal in _rgb(cor):
        valor = canal / 255
        canais.append(valor / 12.92 if valor <= 0.03928 else ((valor + 0.055) / 1.055) ** 2.4)
    return 0.2126 * canais[0] + 0.7152 * canais[1] + 0.0722 * canais[2]


def _contraste(cor_a: str, cor_b: str) -> float:
    clara, escura = sorted((_luminancia(cor_a), _luminancia(cor_b)), reverse=True)
    return (clara + 0.05) / (escura + 0.05)


def _enriquecer_identidade(contexto: dict) -> dict:
    principal = contexto["cor_principal"]
    texto_sobre_principal = "#ffffff" if _contraste(principal, "#ffffff") >= _contraste(principal, "#111827") else "#111827"
    return {
        **contexto,
        "cor_principal_clara": _misturar(principal, "#ffffff", 0.88),
        "cor_principal_escura": _misturar(principal, "#111827", 0.28),
        "cor_principal_hover": _misturar(principal, "#111827", 0.12),
        "cor_principal_superficie": _misturar(principal, "#ffffff", 0.94),
        "cor_borda_marca": _misturar(principal, "#ffffff", 0.72),
        "texto_sobre_principal": texto_sobre_principal,
        "contraste_principal": round(_contraste(principal, texto_sobre_principal), 2),
    }


def identidade_para_contexto(identidade: IdentidadeClube | None) -> dict:
    if not identidade:
        return _enriquecer_identidade(dict(CORES_PADRAO))
    return _enriquecer_identidade({
        "nome_oficial": identidade.nome_oficial or CORES_PADRAO["nome_oficial"],
        "nome_curto": identidade.nome_curto or identidade.nome_oficial or CORES_PADRAO["nome_curto"],
        "logo_principal": identidade.logo_principal,
        "logo_secundario": identidade.logo_secundario,
        "cor_principal": normalizar_cor(identidade.cor_principal, CORES_PADRAO["cor_principal"]),
        "cor_secundaria": normalizar_cor(identidade.cor_secundaria, CORES_PADRAO["cor_secundaria"]),
        "cor_destaque": normalizar_cor(identidade.cor_destaque, CORES_PADRAO["cor_destaque"]),
        "texto_rodape": identidade.texto_rodape or CORES_PADRAO["texto_rodape"],
        "epoca_predefinida": identidade.epoca_predefinida,
    })


def obter_identidade_clube(db) -> dict:
    identidade = db.query(IdentidadeClube).order_by(IdentidadeClube.id.asc()).first()
    return identidade_para_contexto(identidade)


def garantir_identidade_clube(db) -> IdentidadeClube:
    identidade = db.query(IdentidadeClube).order_by(IdentidadeClube.id.asc()).first()
    if identidade:
        return identidade
    from clube_contexto import clube_atual_id
    atual = clube_atual_id()
    if atual is None:
        raise PermissionError("Seleciona explicitamente um clube antes de configurar a identidade.")
    identidade = IdentidadeClube(clube_id=atual, **{
        chave: valor for chave, valor in CORES_PADRAO.items()
        if chave not in {"logo_principal", "logo_secundario"}
    })
    db.add(identidade)
    db.commit()
    db.refresh(identidade)
    return identidade


def caminho_ficheiro_logo(static_dir: Path, url: str | None) -> Path | None:
    """Resolve apenas logos guardados na pasta de branding da aplicação."""
    if not url or not url.startswith("/static/uploads/branding/"):
        return None
    nome = Path(url.rsplit("/", 1)[-1]).name
    caminho = (static_dir / "uploads" / "branding" / nome).resolve()
    pasta = (static_dir / "uploads" / "branding").resolve()
    return caminho if caminho.parent == pasta else None

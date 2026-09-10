import re
import unicodedata

from auth import encriptar_password
from models.jogador import Jogador
from models.utilizador import PerfilEnum, Utilizador


def _identificador_nome(nome: str) -> str:
    partes = [
        re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", parte).encode("ascii", "ignore").decode().lower())
        for parte in (nome or "").split()
    ]
    partes = [parte for parte in partes if parte and any(letra.isalpha() for letra in parte)]
    if not partes:
        return "atleta"
    return partes[0] if len(partes) == 1 else partes[0] + partes[-1]


def criar_acesso_atleta(db, jogador: Jogador) -> tuple[Utilizador, str | None]:
    existente = db.query(Utilizador).execution_options(ignorar_clube=True).filter(
        Utilizador.jogador_id == jogador.id
    ).first()
    if existente:
        return existente, None

    base = _identificador_nome(jogador.nome)
    username = base
    sufixo = 2
    while db.query(Utilizador).execution_options(ignorar_clube=True).filter(
        Utilizador.username == username
    ).first():
        username = f"{base}{sufixo}"
        sufixo += 1
    password = f"{username}1234"
    utilizador = Utilizador(
        clube_id=jogador.clube_id,
        jogador_id=jogador.id,
        nome=jogador.nome,
        username=username,
        email=f"{username}.{jogador.id}@atletas.local",
        password_hash=encriptar_password(password),
        perfil=PerfilEnum.atleta,
        ativo=bool(jogador.ativo),
        deve_alterar_password=True,
    )
    db.add(utilizador)
    return utilizador, password


def sincronizar_acessos_atletas(db) -> int:
    jogadores_com_acesso = {
        jogador_id for (jogador_id,) in db.query(Utilizador.jogador_id).execution_options(
            ignorar_clube=True
        ).filter(Utilizador.jogador_id.isnot(None)).all()
    }
    jogadores = db.query(Jogador).execution_options(ignorar_clube=True).filter(Jogador.ativo.is_(True)).all()
    criados = 0
    for jogador in jogadores:
        if jogador.id not in jogadores_com_acesso:
            criar_acesso_atleta(db, jogador)
            criados += 1
    return criados

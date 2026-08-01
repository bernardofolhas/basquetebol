import hashlib
import secrets
from datetime import datetime, timedelta

from models.recuperacao_password import TokenRecuperacaoPassword

VALIDADE_MINUTOS = 30


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def criar_token_recuperacao(db, utilizador, *, tipo="email", criado_por=None, pedido_ip=None):
    token = secrets.token_urlsafe(32)
    registo = TokenRecuperacaoPassword(
        clube_id=utilizador.clube_id,
        utilizador_id=utilizador.id,
        criado_por_id=getattr(criado_por, "id", None),
        token_hash=hash_token(token),
        tipo=tipo,
        expira_em=datetime.now() + timedelta(minutes=VALIDADE_MINUTOS),
        pedido_ip=pedido_ip,
    )
    db.add(registo)
    db.flush()
    return token, registo


def obter_token_valido(db, token: str, *, tipo: str | None = None, bloquear: bool = False):
    if not token:
        return None
    query = db.query(TokenRecuperacaoPassword).execution_options(ignorar_clube=True).filter(
        TokenRecuperacaoPassword.token_hash == hash_token(token),
        TokenRecuperacaoPassword.utilizado_em.is_(None),
        TokenRecuperacaoPassword.expira_em > datetime.now(),
    )
    if tipo:
        query = query.filter(TokenRecuperacaoPassword.tipo == tipo)
    if bloquear:
        query = query.with_for_update()
    return query.first()


def consumir_token(registo) -> None:
    registo.utilizado_em = datetime.now()


def validar_password(password: str) -> list[str]:
    erros = []
    if len(password) < 10:
        erros.append("A palavra-passe deve ter pelo menos 10 caracteres.")
    if not any(letra.isalpha() for letra in password):
        erros.append("A palavra-passe deve incluir pelo menos uma letra.")
    if not any(letra.isdigit() for letra in password):
        erros.append("A palavra-passe deve incluir pelo menos um número.")
    return erros

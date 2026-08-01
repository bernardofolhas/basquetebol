from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
import bcrypt
from config import config

SECRET_KEY = config.secret_key
ALGORITHM = config.algorithm
ACCESS_TOKEN_EXPIRE_MINUTES = config.access_token_expire_minutes


def encriptar_password(password: str) -> str:
    # Converte a password para bytes e encripta
    password_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password_bytes, salt).decode("utf-8")


def verificar_password(password: str, password_hash: str) -> bool:
    # Compara a password com o hash guardado
    password_bytes = password.encode("utf-8")
    hash_bytes = password_hash.encode("utf-8")
    return bcrypt.checkpw(password_bytes, hash_bytes)


def criar_token(dados: dict) -> str:
    dados_token = dados.copy()
    # Mantemos a expiração em UTC, mas com datetime timezone-aware.
    expiracao = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    dados_token.update({"exp": expiracao})
    token = jwt.encode(dados_token, SECRET_KEY, algorithm=ALGORITHM)
    return token


def verificar_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None

    # ─────────────────────────────────────────────────────────────
# FUNÇÕES DE AUTORIZAÇÃO
# Verificam se o utilizador tem permissão para aceder a recursos
# ─────────────────────────────────────────────────────────────

def obter_utilizador_atual(request, db):
    """Obtém o utilizador autenticado a partir da sessão."""
    from models.utilizador import Utilizador
    token = request.session.get("token")
    if not token:
        return None
    payload = verificar_token(token)
    if not payload:
        return None
    utilizador = db.query(Utilizador).execution_options(ignorar_clube=True).filter(
        Utilizador.username == payload.get("sub")
    ).first()
    if not utilizador:
        return None
    if int(payload.get("sv", 0)) != int(utilizador.sessao_versao or 0):
        return None
    if utilizador.perfil.value != "superadministrador":
        from clube_contexto import clube_atual_id
        if clube_atual_id() != utilizador.clube_id:
            return None
    return utilizador


def verificar_perfil(utilizador, perfis_permitidos: list) -> bool:
    """
    Verifica se o utilizador tem um dos perfis permitidos.
    Ex: verificar_perfil(utilizador, ["administrador", "coordenador"])
    """
    if not utilizador:
        return False
    return utilizador.perfil.value in perfis_permitidos


def verificar_acesso_equipa(utilizador, equipa_id: int, db) -> bool:
    """
    Verifica se o utilizador tem acesso a uma equipa específica.
    - administrador e coordenador: acesso a tudo
    - treinador: só às suas equipas
    """
    if not utilizador:
        return False

    from models.equipa import Equipa
    equipa = db.query(Equipa).filter(Equipa.id == equipa_id).first()
    if not equipa:
        return False
    if utilizador.perfil.value != "superadministrador" and equipa.clube_id != utilizador.clube_id:
        return False

    if utilizador.perfil.value == "superadministrador":
        from clube_contexto import clube_atual_id
        return clube_atual_id() == equipa.clube_id

    # Administrador e coordenador têm acesso total dentro do clube atual.
    if utilizador.perfil.value in ["administrador", "coordenador"]:
        return True

    # Treinador só tem acesso às suas equipas
    if utilizador.perfil.value == "treinador":
        # Verifica se o utilizador tem treinador associado
        if not utilizador.treinador_id:
            return False
        from models.treinador import Treinador
        treinador = db.query(Treinador).filter(
            Treinador.id == utilizador.treinador_id
        ).first()
        if not treinador:
            return False
        # Verifica se a equipa está nas equipas do treinador
        if treinador.clube_id != utilizador.clube_id:
            return False
        equipas_ids = [e.id for e in treinador.equipas]
        return equipa_id in equipas_ids

    return False

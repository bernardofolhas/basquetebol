"""
Dependências FastAPI para autenticação e autorização.

Substituem o padrão repetitivo de 3-4 linhas em cada rota por
dependências injectadas via Depends(), com exceções personalizadas
que são convertidas em RedirectResponse pelos handlers em main.py.
"""
from fastapi import Depends, Request
from sqlalchemy.orm import Session

from auth import obter_utilizador_atual, verificar_perfil, verificar_acesso_equipa
from database import get_db


# ─────────────────────────────────────────────────────────────
# EXCEÇÕES PERSONALIZADAS
# ─────────────────────────────────────────────────────────────

class NaoAutenticado(Exception):
    """O utilizador não está autenticado (sem token de sessão válido)."""


class SemPermissao(Exception):
    """O utilizador está autenticado mas não tem o perfil necessário."""
    def __init__(self, redirect_para: str = "/dashboard", status_code: int = 302) -> None:
        self.redirect_para = redirect_para
        self.status_code = status_code


class AcessoNegado(Exception):
    """O utilizador não tem acesso ao recurso específico (equipa, etc.)."""
    def __init__(self, redirect_para: str = "/dashboard") -> None:
        self.redirect_para = redirect_para


# ─────────────────────────────────────────────────────────────
# DEPENDÊNCIAS DE AUTENTICAÇÃO
# ─────────────────────────────────────────────────────────────

def exigir_autenticacao(request: Request, db: Session = Depends(get_db)):
    """Qualquer utilizador autenticado, independentemente do perfil."""
    utilizador = obter_utilizador_atual(request, db)
    if not utilizador:
        raise NaoAutenticado()
    return utilizador


def exigir_qualquer_perfil(request: Request, db: Session = Depends(get_db)):
    """Utilizador autenticado com qualquer perfil válido do sistema."""
    utilizador = obter_utilizador_atual(request, db)
    if not utilizador:
        raise NaoAutenticado()
    if not verificar_perfil(utilizador, ["administrador", "coordenador", "treinador"]):
        raise NaoAutenticado()
    return utilizador


def exigir_coordenacao(request: Request, db: Session = Depends(get_db)):
    """Apenas administrador ou coordenador."""
    utilizador = obter_utilizador_atual(request, db)
    if not utilizador:
        raise NaoAutenticado()
    perfis = ["administrador", "coordenador"]
    if getattr(request.state, "clube_atual", None):
        perfis.append("superadministrador")
    if not verificar_perfil(utilizador, perfis):
        raise SemPermissao("/dashboard")
    return utilizador


def exigir_admin(request: Request, db: Session = Depends(get_db)):
    """Apenas administrador."""
    utilizador = obter_utilizador_atual(request, db)
    if not utilizador:
        raise NaoAutenticado()
    perfis = ["administrador"]
    if getattr(request.state, "clube_atual", None):
        perfis.append("superadministrador")
    if not verificar_perfil(utilizador, perfis):
        raise SemPermissao("/dashboard", status_code=403)
    return utilizador


def exigir_superadmin(request: Request, db: Session = Depends(get_db)):
    utilizador = obter_utilizador_atual(request, db)
    if not utilizador:
        raise NaoAutenticado()
    if not verificar_perfil(utilizador, ["superadministrador"]):
        raise SemPermissao("/dashboard", status_code=403)
    return utilizador


# ─────────────────────────────────────────────────────────────
# VERIFICAÇÃO DE ACESSO A EQUIPA (usada dentro das rotas)
# ─────────────────────────────────────────────────────────────

def verificar_ou_negar_equipa(utilizador, equipa_id: int, db: Session) -> None:
    """Lança AcessoNegado se o utilizador não tiver acesso à equipa."""
    if not verificar_acesso_equipa(utilizador, equipa_id, db):
        raise AcessoNegado("/dashboard")

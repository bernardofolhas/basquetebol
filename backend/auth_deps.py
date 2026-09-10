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


def exigir_atleta(request: Request, db: Session = Depends(get_db)):
    """Apenas uma conta associada a uma ficha de atleta."""
    utilizador = exigir_autenticacao(request, db)
    if utilizador.perfil.value != "atleta" or not utilizador.jogador_id:
        raise SemPermissao("/dashboard")
    return utilizador


def exigir_qualquer_perfil(request: Request, db: Session = Depends(get_db)):
    """Utilizador autenticado com qualquer perfil válido do sistema."""
    utilizador = obter_utilizador_atual(request, db)
    if not utilizador:
        raise NaoAutenticado()
    perfis = _perfis_com_superadmin_em_apoio(
        request,
        ["administrador", "coordenador", "treinador", "secretaria", "staff"],
    )
    if not verificar_perfil(utilizador, perfis):
        raise NaoAutenticado()
    return utilizador


def _perfis_com_superadmin_em_apoio(request: Request, perfis: list[str]) -> list[str]:
    permitidos = list(perfis)
    if getattr(request.state, "clube_atual", None):
        permitidos.append("superadministrador")
    return permitidos


def exigir_coordenacao(request: Request, db: Session = Depends(get_db)):
    """Apenas administrador ou coordenador."""
    utilizador = obter_utilizador_atual(request, db)
    if not utilizador:
        raise NaoAutenticado()
    perfis = _perfis_com_superadmin_em_apoio(request, ["administrador", "coordenador"])
    if not verificar_perfil(utilizador, perfis):
        raise SemPermissao("/dashboard")
    return utilizador


def exigir_operacao_desportiva(request: Request, db: Session = Depends(get_db)):
    """Perfis que podem consultar a operação técnica e desportiva."""
    utilizador = obter_utilizador_atual(request, db)
    if not utilizador:
        raise NaoAutenticado()
    perfis = _perfis_com_superadmin_em_apoio(
        request,
        ["administrador", "coordenador", "treinador", "staff"],
    )
    if not verificar_perfil(utilizador, perfis):
        raise SemPermissao("/dashboard")
    return utilizador


def exigir_scouting(request: Request, db: Session = Depends(get_db)):
    """Scouting é reservado à equipa técnica com responsabilidade técnica."""
    utilizador = obter_utilizador_atual(request, db)
    if not utilizador:
        raise NaoAutenticado()
    perfis = _perfis_com_superadmin_em_apoio(
        request,
        ["administrador", "coordenador", "treinador"],
    )
    if not verificar_perfil(utilizador, perfis):
        raise SemPermissao("/dashboard", status_code=403)
    return utilizador


def exigir_secretaria(request: Request, db: Session = Depends(get_db)):
    """Perfis autorizados a tratar processos administrativos do clube."""
    utilizador = obter_utilizador_atual(request, db)
    if not utilizador:
        raise NaoAutenticado()
    perfis = _perfis_com_superadmin_em_apoio(
        request,
        ["administrador", "coordenador", "secretaria"],
    )
    if not verificar_perfil(utilizador, perfis):
        raise SemPermissao("/dashboard")
    return utilizador


def exigir_admin(request: Request, db: Session = Depends(get_db)):
    """Apenas administrador."""
    utilizador = obter_utilizador_atual(request, db)
    if not utilizador:
        raise NaoAutenticado()
    perfis = _perfis_com_superadmin_em_apoio(request, ["administrador"])
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

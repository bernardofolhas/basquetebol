"""Registo centralizado de operações administrativas relevantes."""

from models.auditoria import RegistoAuditoria
from clube_contexto import clube_atual_id


def registar_auditoria(
    db,
    utilizador,
    acao: str,
    entidade: str,
    entidade_id: int | None = None,
    detalhes: str | None = None,
    request=None,
) -> RegistoAuditoria:
    registo = RegistoAuditoria(
        clube_id=clube_atual_id() or getattr(utilizador, "clube_id", None),
        utilizador_id=getattr(utilizador, "id", None),
        utilizador_username=getattr(utilizador, "username", None),
        acao=acao,
        entidade=entidade,
        entidade_id=entidade_id,
        detalhes=detalhes,
        endereco_ip=getattr(getattr(request, "client", None), "host", None),
    )
    db.add(registo)
    return registo

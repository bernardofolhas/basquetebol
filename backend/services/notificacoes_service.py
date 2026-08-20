"""Notificações operacionais pequenas e privadas, sem depender de serviços externos."""

from models.notificacao import Notificacao
from models.utilizador import Utilizador


def criar_notificacoes_para_equipa(db, equipa, titulo: str, mensagem: str, link: str | None = None) -> int:
    """Avisa apenas utilizadores treinadores ligados à equipa indicada."""
    treinador_ids = [treinador.id for treinador in getattr(equipa, "treinadores", [])]
    if not treinador_ids:
        return 0
    utilizadores = db.query(Utilizador).filter(
        Utilizador.treinador_id.in_(treinador_ids),
        Utilizador.ativo.is_(True),
    ).all()
    for utilizador in utilizadores:
        db.add(Notificacao(
            clube_id=equipa.clube_id,
            utilizador_id=utilizador.id,
            titulo=titulo,
            mensagem=mensagem,
            link=link,
        ))
    return len(utilizadores)


def obter_notificacoes_utilizador(db, utilizador, limite: int = 8) -> list:
    return db.query(Notificacao).filter(
        Notificacao.utilizador_id == utilizador.id,
    ).order_by(Notificacao.lida.asc(), Notificacao.criado_em.desc()).limit(limite).all()

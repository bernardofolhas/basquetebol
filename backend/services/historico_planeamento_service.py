from models.historico_planeamento import HistoricoPlaneamentoClube


def registar_historico_planeamento(
    db,
    utilizador,
    entidade: str,
    entidade_id: int,
    acao: str,
    detalhes: str | None = None,
) -> HistoricoPlaneamentoClube:
    registo = HistoricoPlaneamentoClube(
        utilizador_id=getattr(utilizador, "id", None),
        utilizador_username=getattr(utilizador, "username", None),
        entidade=entidade,
        entidade_id=entidade_id,
        acao=acao,
        detalhes=detalhes,
    )
    db.add(registo)
    return registo

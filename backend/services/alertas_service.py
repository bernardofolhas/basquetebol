from datetime import date, datetime, timedelta


def _obter_intervalo_alertas():
    """Devolve a data actual e o limite temporal para alertas próximos."""
    hoje = date.today()
    limite = hoje + timedelta(days=30)
    return hoje, limite


def obter_alertas_treinador(db, equipa_ids: list):
    """
    Devolve os alertas relevantes para um treinador.

    Os alertas são limitados às equipas fornecidas e mantêm o formato
    actualmente esperado pelos templates do dashboard do treinador.
    """
    from models.jogador import Jogador
    from models.atribuicao_espaco_semanal import AtribuicaoEspacoSemanal, EstadoAtribuicaoEspacoEnum

    hoje, limite = _obter_intervalo_alertas()
    alertas = []

    if not equipa_ids:
        return alertas

    jogadores = db.query(Jogador).filter(
        Jogador.equipa_id.in_(equipa_ids)
    ).order_by(Jogador.nome).all()

    for jogador in jogadores:
        if hasattr(jogador, "exame_medico_validade") and jogador.exame_medico_validade:
            if hoje <= jogador.exame_medico_validade <= limite:
                alertas.append({
                    "tipo": "exame",
                    "mensagem": (
                        f"{jogador.nome} "
                        f"— exame médico expira em {jogador.exame_medico_validade}"
                    ),
                    "urgente": jogador.exame_medico_validade <= hoje
                })

        if hasattr(jogador, "inscricao_estado") and jogador.inscricao_estado == "pendente":
            alertas.append({
                "tipo": "inscricao",
                "mensagem": f"{jogador.nome} — inscrição pendente",
                "urgente": False
            })

    previsoes_recentes = db.query(AtribuicaoEspacoSemanal).filter(
        AtribuicaoEspacoSemanal.equipa_id.in_(equipa_ids),
        AtribuicaoEspacoSemanal.estado == EstadoAtribuicaoEspacoEnum.publicado,
        AtribuicaoEspacoSemanal.data >= hoje,
        AtribuicaoEspacoSemanal.data <= limite,
        AtribuicaoEspacoSemanal.atualizado_em >= datetime.now() - timedelta(days=7),
    ).order_by(AtribuicaoEspacoSemanal.data, AtribuicaoEspacoSemanal.hora_inicio).limit(8).all()
    for previsao in previsoes_recentes:
        alertas.append({
            "tipo": "planeamento_semanal",
            "mensagem": (
                f"Previsão do clube atualizada: {previsao.data.strftime('%d/%m/%Y')} "
                f"{previsao.hora_inicio}-{previsao.hora_fim} · "
                f"{previsao.espaco.nome if previsao.espaco else 'espaço por definir'}"
            ),
            "urgente": False,
        })

    alertas.sort(key=lambda alerta: alerta["urgente"], reverse=True)
    return alertas


def obter_alertas_globais(db):
    """
    Devolve os alertas globais para coordenador e administrador.

    Mantém o mesmo formato actualmente usado nos dashboards globais.
    """
    from models.jogador import Jogador

    hoje, limite = _obter_intervalo_alertas()
    alertas = []
    jogadores = db.query(Jogador).all()

    for jogador in jogadores:
        if hasattr(jogador, "exame_medico_validade") and jogador.exame_medico_validade:
            if jogador.exame_medico_validade <= limite:
                alertas.append({
                    "mensagem": (
                        f"{jogador.nome} "
                        f"({jogador.equipa.nome if jogador.equipa else '?'}) "
                        f"— exame médico expira em {jogador.exame_medico_validade}"
                    ),
                    "urgente": jogador.exame_medico_validade <= hoje
                })

        if hasattr(jogador, "inscricao_estado") and jogador.inscricao_estado == "pendente":
            alertas.append({
                "mensagem": (
                    f"{jogador.nome} "
                    f"({jogador.equipa.nome if jogador.equipa else '?'}) "
                    "— inscrição pendente"
                ),
                "urgente": False
            })

    alertas.sort(key=lambda alerta: alerta["urgente"], reverse=True)
    return alertas

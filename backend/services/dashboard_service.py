from calendar import monthrange
from datetime import date, timedelta
from services.alertas_service import obter_alertas_globais, obter_alertas_treinador
from services.operacao_clube_service import (
    obter_dashboard_carga_treino,
    obter_dashboard_clube_operacional,
    obter_dashboard_ocupacao_espacos,
    obter_dashboard_planeado_executado,
    obter_dashboard_sincronizacao,
    obter_resumo_operacional_mensal,
)
from services.planeamento_integrado_service import apresentar_treinos_por_perfil, obter_dashboard_planeamento_intervalo
from services.sessao_workflow import normalizar_estado_sessao


def _obter_intervalo_alertas():
    """Devolve a data actual e o limite temporal para alertas próximos."""
    hoje = date.today()
    limite = hoje + timedelta(days=30)
    return hoje, limite


def _obter_nome_mes_portugues(mes: int) -> str:
    """Converte o número do mês para um nome legível em português."""
    meses = {
        1: "Janeiro",
        2: "Fevereiro",
        3: "Março",
        4: "Abril",
        5: "Maio",
        6: "Junho",
        7: "Julho",
        8: "Agosto",
        9: "Setembro",
        10: "Outubro",
        11: "Novembro",
        12: "Dezembro",
    }
    return meses.get(mes, str(mes))


def _obter_itens_agenda(db, data_inicio, data_fim, equipa_ids=None, perfil_visual=None):
    """Obtém itens integrados, evitando duplicados quando há várias equipas."""
    if equipa_ids is None:
        itens = obter_dashboard_planeamento_intervalo(db, data_inicio, data_fim)["itens"]
        return apresentar_treinos_por_perfil(itens, perfil_visual)
    if not equipa_ids:
        return []

    itens_por_id = {}
    for equipa_id in equipa_ids:
        dashboard = obter_dashboard_planeamento_intervalo(
            db,
            data_inicio,
            data_fim,
            equipa_id=equipa_id,
        )
        for item in dashboard["itens"]:
            itens_por_id[item["id"]] = item
    itens = sorted(
        itens_por_id.values(),
        key=lambda item: (item["data"], item["hora_inicio"] or "99:99", item["titulo"].lower()),
    )
    return apresentar_treinos_por_perfil(itens, perfil_visual)


def obter_painel_operacional(
    db,
    equipa_ids=None,
    hoje=None,
    *,
    incluir_pendencias_secretaria=True,
    perfil_visual=None,
):
    """Constrói agenda e tarefas acionáveis para a página inicial."""
    from models.assiduidade import RegistoAssiduidade
    from models.jogador import Jogador
    from models.jogo import Jogo
    from models.planeamento import SessaoTreino
    from models.treino import PlanoTreino

    hoje = hoje or date.today()
    limite = hoje + timedelta(days=7)
    itens = _obter_itens_agenda(db, hoje, limite, equipa_ids, perfil_visual)
    agenda_hoje = [item for item in itens if item["data"] == hoje]
    agenda_proxima = [item for item in itens if hoje <= item["data"] <= limite]
    tarefas = []

    sessoes_ids = [
        int(item["id"].split("-", 1)[1])
        for item in agenda_proxima
        if item["id"].startswith("sessao-")
    ]
    jogos_ids = [
        int(item["id"].split("-", 1)[1])
        for item in agenda_proxima
        if item["id"].startswith("jogo-")
    ]
    sessoes = db.query(SessaoTreino).filter(SessaoTreino.id.in_(sessoes_ids)).all() if sessoes_ids else []
    jogos = db.query(Jogo).filter(Jogo.id.in_(jogos_ids)).all() if jogos_ids else []
    sessoes_por_id = {sessao.id: sessao for sessao in sessoes}
    jogos_por_id = {jogo.id: jogo for jogo in jogos}

    def _equipa_id_sessao(sessao):
        try:
            return sessao.microciclo.mesociclo.macrociclo.equipa_id
        except Exception:
            return None

    def _adicionar(item, titulo, link, urgente=False, detalhe=None):
        tarefas.append({
            "item": item,
            "titulo": titulo,
            "urgente": urgente,
            "link": link,
            "detalhe": detalhe,
        })

    for item in agenda_proxima:
        if item["id"].startswith("sessao-"):
            sessao = sessoes_por_id.get(int(item["id"].split("-", 1)[1]))
            if not sessao:
                continue
            estado = normalizar_estado_sessao(item.get("estado"))
            plano = sessao.plano_treino
            if estado in {"planeada", "confirmada"}:
                if not plano or not plano.exercicios:
                    _adicionar(item, "Completar plano de treino", item["link"], item["data"] == hoje)
                else:
                    _adicionar(
                        item,
                        "Confirmar sessão" if estado == "planeada" else "Abrir sessão",
                        item.get("acao_link") or item["link"],
                        item["data"] == hoje,
                    )
            elif estado == "executada":
                equipa_id = _equipa_id_sessao(sessao)
                total_jogadores = db.query(Jogador).filter(Jogador.equipa_id == equipa_id).count() if equipa_id else 0
                registos = db.query(RegistoAssiduidade).filter(RegistoAssiduidade.sessao_id == sessao.id).all()
                por_registar = len(registos) < total_jogadores or any(
                    (registo.estado or "").strip().lower() == "por_registar" for registo in registos
                )
                _adicionar(
                    item,
                    "Registar presenças" if por_registar else "Registar sessão",
                    f"/assiduidade/sessoes/{sessao.id}" if por_registar else item["link"],
                    item["data"] == hoje,
                )
            elif estado == "registada":
                _adicionar(item, "Rever sessão", item["link"])
        elif item["id"].startswith("jogo-"):
            jogo = jogos_por_id.get(int(item["id"].split("-", 1)[1]))
            if not jogo:
                continue
            if not jogo.convocados:
                _adicionar(item, "Criar convocatória", f"/jogos/{jogo.id}", item["data"] == hoje)
            if not jogo.plano:
                _adicionar(item, "Preparar plano de jogo", f"/jogos/{jogo.id}/plano", item["data"] == hoje)
            elif item["data"] == hoje:
                _adicionar(item, "Abrir jogo", item["link"], True)

    if equipa_ids is None:
        from models.documento_jogador import DocumentoJogador
        from models.planeamento_clube import PlanoSemanalClube
        from services.operacao_clube_service import obter_dashboard_ocupacao_espacos

        dashboard_espacos = obter_dashboard_ocupacao_espacos(db, hoje)
        for conflito in dashboard_espacos.get("conflitos", [])[:3]:
            item = {
                "data": conflito["data"],
                "equipa_nome": conflito["espaco"],
                "titulo": "Conflito de espaço",
            }
            _adicionar(item, "Resolver conflito de espaço", "/dashboard/clube/espacos", True, conflito["mensagem"])

        if incluir_pendencias_secretaria:
            pendencias_secretaria = 0
            jogadores = db.query(Jogador).all()
            for jogador in jogadores:
                if jogador.inscricao_estado != "completa" or not jogador.exame_medico_validade:
                    pendencias_secretaria += 1
                pendencias_secretaria += db.query(DocumentoJogador).filter(
                    DocumentoJogador.jogador_id == jogador.id,
                    DocumentoJogador.estado.in_(["pendente", "expirado"]),
                ).count()
            if pendencias_secretaria:
                item = {"data": hoje, "equipa_nome": "Clube", "titulo": "Pendências administrativas"}
                _adicionar(item, f"Rever {pendencias_secretaria} pendência(s) administrativas", "/secretaria/pendencias")

        plano_semanal = db.query(PlanoSemanalClube).filter(
            PlanoSemanalClube.data_inicio <= limite,
            PlanoSemanalClube.data_fim >= hoje,
        ).order_by(PlanoSemanalClube.data_inicio.asc()).first()
        if not plano_semanal:
            item = {"data": hoje, "equipa_nome": "Clube", "titulo": "Plano semanal"}
            _adicionar(item, "Criar plano semanal", "/planeamento-clube/semanal")
        elif plano_semanal.estado != "ativo":
            item = {"data": plano_semanal.data_inicio, "equipa_nome": "Clube", "titulo": plano_semanal.titulo}
            _adicionar(item, "Publicar plano semanal", f"/planeamento-clube/semanal/{plano_semanal.id}")

    return {
        "agenda_hoje": agenda_hoje,
        "agenda_proxima": agenda_proxima,
        "tarefas": tarefas,
        "resumo_agenda": {
            "hoje": len(agenda_hoje),
            "proximos_7_dias": len(agenda_proxima),
            "tarefas": len(tarefas),
        },
    }


def _obter_planeamento_mensal_atual(db):
    """
    Obtém planeamento mensal do mês atual + dados operacionais.

    Returns:
    {
      "mensal": PlaneamentoClubeMensal | None,
      "resumo_equipas": [
        {
          "equipa": Equipa,
          "treinador_principal": Treinador | None,
          "proximos_treinos": [
            {"data": date, "hora": str, "espaco": str, "tipo": str}
          ],
          "proximos_jogos": [Jogo],
        }
      ],
      "mes_atual_label": str,
    }
    """
    from models.planeamento_clube import PlaneamentoClubeMensal

    hoje = date.today()
    ano_atual = hoje.year
    mes_atual = hoje.month
    mes_atual_label = f"{_obter_nome_mes_portugues(mes_atual)} {ano_atual}"

    mensal = db.query(PlaneamentoClubeMensal).filter(
        PlaneamentoClubeMensal.ano == ano_atual,
        PlaneamentoClubeMensal.mes == mes_atual
    ).order_by(PlaneamentoClubeMensal.id.desc()).first()

    if not mensal:
        return {
            "mensal": None,
            "resumo_equipas": [],
            "mes_atual_label": mes_atual_label,
        }

    resumo_operacional = obter_resumo_operacional_mensal(
        db,
        mensal,
        data_minima=hoje,
    )
    resumo_equipas = []
    for item in resumo_operacional["resumo_equipas"]:
        resumo_equipas.append({
            "equipa": item["equipa"],
            "treinador_principal": item["treinador_principal"],
            "proximos_treinos": item["treinos"],
            "proximos_jogos": item["jogos"],
        })

    return {
        "mensal": mensal,
        "resumo_equipas": resumo_equipas,
        "mes_atual_label": mes_atual_label,
    }


def _obter_dados_base_dashboard_global(db, hoje, limite, incluir_total_utilizadores=False):
    """
    Constrói os dados comuns aos dashboards de coordenador e administrador.

    Esta função mantém a lógica simples e próxima da implementação actual,
    evitando joins frágeis e privilegiando queries ORM fáceis de seguir.
    """
    from models.equipa import Equipa
    from models.treinador import Treinador
    from models.jogador import Jogador
    from models.jogo import Jogo

    contexto = {
        "total_equipas": db.query(Equipa).count(),
        "total_treinadores": db.query(Treinador).count(),
        "total_jogadores": db.query(Jogador).count(),
        "proximos_jogos": db.query(Jogo).filter(
            Jogo.data >= hoje
        ).order_by(Jogo.data).limit(5).all(),
        "ultimos_resultados": db.query(Jogo).filter(
            Jogo.pontos_nos != None,
            Jogo.pontos_adversario != None
        ).order_by(Jogo.data.desc()).limit(5).all(),
    }

    if incluir_total_utilizadores:
        from models.utilizador import Utilizador

        contexto["total_utilizadores"] = db.query(Utilizador).count()

    equipas = db.query(Equipa).all()
    dados_equipas = []

    for equipa in equipas:
        proximo = db.query(Jogo).filter(
            Jogo.equipa_id == equipa.id,
            Jogo.data >= hoje
        ).order_by(Jogo.data).first()

        ultimo = db.query(Jogo).filter(
            Jogo.equipa_id == equipa.id,
            Jogo.pontos_nos != None,
            Jogo.pontos_adversario != None
        ).order_by(Jogo.data.desc()).first()

        dados_equipas.append({
            "equipa": equipa,
            "proximo_jogo": proximo,
            "ultimo_resultado": ultimo
        })

    contexto["dados_equipas"] = dados_equipas
    contexto["alertas"] = obter_alertas_globais(db)
    return contexto


def get_dashboard_treinador(db, utilizador):
    """Constrói o contexto do dashboard do treinador."""
    from models.treinador import Treinador
    from models.jogo import Jogo
    from models.planeamento import SessaoTreino
    from models.assiduidade import RegistoAssiduidade
    from services.assiduidade_service import calcular_resumo_assiduidade

    hoje, limite = _obter_intervalo_alertas()

    equipas = []
    if utilizador.treinador_id:
        treinador = db.query(Treinador).filter(
            Treinador.id == utilizador.treinador_id
        ).first()

        if treinador:
            equipas = treinador.equipas

    equipa_ids = [equipa.id for equipa in equipas]
    alertas = obter_alertas_treinador(db, equipa_ids)
    dados_equipas = []

    for equipa in equipas:
        proximo_jogo = db.query(Jogo).filter(
            Jogo.equipa_id == equipa.id,
            Jogo.data >= hoje
        ).order_by(Jogo.data).first()

        ultimo_resultado = db.query(Jogo).filter(
            Jogo.equipa_id == equipa.id,
            Jogo.pontos_nos != None,
            Jogo.pontos_adversario != None
        ).order_by(Jogo.data.desc()).first()

        proxima_sessao = None
        sessoes_futuras = db.query(SessaoTreino).filter(
            SessaoTreino.data >= hoje,
            SessaoTreino.e_jogo == False,
            SessaoTreino.ativa == True,
        ).order_by(SessaoTreino.data).all()

        for sessao in sessoes_futuras:
            try:
                equipa_sessao = sessao.microciclo.mesociclo.macrociclo.equipa
                if equipa_sessao and equipa_sessao.id == equipa.id:
                    proxima_sessao = sessao
                    break
            except Exception:
                continue

        ultimas_sessoes_equipa = []
        sessoes_passadas = db.query(SessaoTreino).filter(
            SessaoTreino.data <= hoje,
            SessaoTreino.e_jogo == False,
            SessaoTreino.ativa == True,
        ).order_by(SessaoTreino.data.desc()).all()

        for sessao in sessoes_passadas:
            try:
                equipa_sessao = sessao.microciclo.mesociclo.macrociclo.equipa
                if equipa_sessao and equipa_sessao.id == equipa.id:
                    ultimas_sessoes_equipa.append(sessao)
            except Exception:
                continue

            if len(ultimas_sessoes_equipa) == 3:
                break

        assiduidade_recente = []

        for sessao in ultimas_sessoes_equipa:
            registos = db.query(RegistoAssiduidade).filter(
                RegistoAssiduidade.sessao_id == sessao.id
            ).all()

            resumo_assiduidade = calcular_resumo_assiduidade(registos)

            assiduidade_recente.append({
                "sessao": sessao,
                "presentes": resumo_assiduidade["presentes"],
                "total": resumo_assiduidade["total"],
                "percentagem": resumo_assiduidade["percentagem"],
                "por_estado": resumo_assiduidade["por_estado"],
            })

        from models.jogador import Jogador

        jogadores_equipa = db.query(Jogador).filter(
            Jogador.equipa_id == equipa.id
        ).order_by(Jogador.nome).all()

        dados_equipas.append({
            "equipa": equipa,
            "proximo_jogo": proximo_jogo,
            "ultimo_resultado": ultimo_resultado,
            "proxima_sessao": proxima_sessao,
            "total_jogadores": len(jogadores_equipa),
            "jogadores_equipa": jogadores_equipa,
            "assiduidade_recente": assiduidade_recente
        })

    return {
        "utilizador": utilizador,
        "dados_equipas": dados_equipas,
        "alertas": alertas,
        **obter_painel_operacional(db, equipa_ids=equipa_ids),
    }


def get_dashboard_coordenador(db, utilizador):
    """Constrói o contexto do dashboard do coordenador."""
    hoje, limite = _obter_intervalo_alertas()
    contexto = _obter_dados_base_dashboard_global(db, hoje, limite)
    contexto_planeamento = _obter_planeamento_mensal_atual(db)
    contexto["utilizador"] = utilizador
    contexto["planeamento_mensal"] = contexto_planeamento["mensal"]
    contexto["resumo_equipas"] = contexto_planeamento["resumo_equipas"]
    contexto["mes_atual_label"] = contexto_planeamento["mes_atual_label"]
    contexto.update(obter_painel_operacional(
        db,
        incluir_pendencias_secretaria=False,
        perfil_visual="coordenador",
    ))
    # O coordenador acompanha a operação do clube, não a preparação técnica individual.
    contexto["tarefas"] = [
        tarefa for tarefa in contexto["tarefas"]
        if tarefa["titulo"] != "Completar plano de treino"
    ]
    contexto["resumo_agenda"]["tarefas"] = len(contexto["tarefas"])
    inicio_mes = date(hoje.year, hoje.month, 1)
    fim_mes = date(hoje.year, hoje.month, monthrange(hoje.year, hoje.month)[1])
    contexto["calendario_mes"] = obter_dashboard_planeamento_intervalo(
        db,
        inicio_mes,
        fim_mes,
    )["meses"][0]
    return contexto


def get_dashboard_admin(db, utilizador):
    """Constrói o contexto do dashboard do administrador."""
    hoje, limite = _obter_intervalo_alertas()
    contexto = _obter_dados_base_dashboard_global(
        db,
        hoje,
        limite,
        incluir_total_utilizadores=True
    )
    contexto_planeamento = _obter_planeamento_mensal_atual(db)
    contexto["utilizador"] = utilizador
    contexto["planeamento_mensal"] = contexto_planeamento["mensal"]
    contexto["resumo_equipas"] = contexto_planeamento["resumo_equipas"]
    contexto["mes_atual_label"] = contexto_planeamento["mes_atual_label"]
    contexto.update(obter_painel_operacional(db, perfil_visual="administrador"))
    return contexto


def get_dashboard_clube(db, utilizador):
    """Constrói o contexto do dashboard geral operacional do clube."""
    contexto = obter_dashboard_clube_operacional(db)
    contexto["utilizador"] = utilizador
    return contexto


def get_dashboard_clube_espacos(db, utilizador):
    """Constrói o contexto do dashboard operacional de ocupação de espaços."""
    contexto = obter_dashboard_ocupacao_espacos(db)
    contexto["utilizador"] = utilizador
    return contexto


def get_dashboard_clube_carga(db, utilizador):
    """Constrói o contexto do dashboard operacional de carga de treino."""
    contexto = obter_dashboard_carga_treino(db)
    contexto["utilizador"] = utilizador
    return contexto


def get_dashboard_clube_executado(db, utilizador):
    """Constrói o contexto do dashboard de sessões planeadas, ativas e desativadas."""
    contexto = obter_dashboard_planeado_executado(db)
    contexto["utilizador"] = utilizador
    return contexto


def get_dashboard_clube_sincronizacao(db, utilizador):
    """Constrói o contexto do dashboard operacional de sincronização."""
    contexto = obter_dashboard_sincronizacao(db)
    contexto["utilizador"] = utilizador
    return contexto

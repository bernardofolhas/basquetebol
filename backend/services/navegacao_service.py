"""Contexto comum da navegação, sem lógica de apresentação nos templates."""

from collections import OrderedDict

from models.utilizador import PerfilEnum
from models.notificacao import Notificacao
from services.dashboard_service import obter_painel_operacional
from services.notificacoes_service import obter_notificacoes_utilizador


GRUPOS_PENDENCIAS = OrderedDict([
    ("treino", "Sessões e treinos"),
    ("jogos", "Jogos"),
    ("planeamento", "Planeamento"),
    ("espacos", "Espaços"),
    ("secretaria", "Secretaria"),
])


def _equipas_permitidas(utilizador) -> list:
    if utilizador.perfil != PerfilEnum.treinador:
        return []
    treinador = getattr(utilizador, "treinador", None)
    return list(getattr(treinador, "equipas", []) or [])


def _grupo_tarefa(tarefa: dict) -> str:
    texto = f"{tarefa.get('titulo', '')} {tarefa.get('link', '')}".lower()
    if "jogo" in texto or "convocat" in texto:
        return "jogos"
    if "espaço" in texto or "espaco" in texto:
        return "espacos"
    if "secretaria" in texto or "administrativ" in texto or "document" in texto:
        return "secretaria"
    if "plano semanal" in texto or "planeamento-clube" in texto:
        return "planeamento"
    return "treino"


def _agrupar_pendencias(tarefas: list[dict]) -> list[dict]:
    grupos = {chave: [] for chave in GRUPOS_PENDENCIAS}
    for tarefa in tarefas:
        item = dict(tarefa)
        item["prioridade"] = "alta" if tarefa.get("urgente") else "normal"
        grupos[_grupo_tarefa(tarefa)].append(item)

    resultado = []
    for chave, label in GRUPOS_PENDENCIAS.items():
        itens = sorted(
            grupos[chave],
            key=lambda item: (
                not item.get("urgente", False),
                item.get("item", {}).get("data"),
                item.get("titulo", "").lower(),
            ),
        )
        if itens:
            resultado.append({"chave": chave, "label": label, "itens": itens})
    return resultado


def _acoes_rapidas(utilizador, equipas: list) -> list[dict]:
    perfil = utilizador.perfil.value
    if perfil == "secretaria":
        return [{
            "label": "Rever pendências",
            "descricao": "Documentos, inscrições e exames",
            "link": "/secretaria/pendencias",
            "icone": "secretaria",
        }]
    acoes = [
        {"label": "Abrir calendário", "descricao": "Ver a operação do clube", "link": "/calendario", "icone": "calendario"},
    ]
    if equipas:
        equipa = equipas[0]
        acoes.extend([
            {"label": "Preparar treino", "descricao": equipa.nome, "link": f"/planeamento/equipas/{equipa.id}/anuais", "icone": "treino"},
            {"label": "Criar convocatória", "descricao": equipa.nome, "link": f"/jogos/equipas/{equipa.id}", "icone": "jogo"},
        ])
    if perfil in {"administrador", "coordenador", "superadministrador"}:
        acoes.extend([
            {"label": "Criar atividade", "descricao": "No calendário operacional", "link": "/calendario", "icone": "atividade"},
            {"label": "Planear semana", "descricao": "Planeamento do clube", "link": "/planeamento-clube/semanal", "icone": "semana"},
            {"label": "Adicionar jogador", "descricao": "Novo registo", "link": "/jogadores/novo", "icone": "jogador"},
        ])
    return acoes


def obter_contexto_navegacao(db, utilizador, clube_atual=None) -> dict:
    """Devolve apenas contexto permitido para a barra global."""
    modo_plataforma = utilizador.perfil == PerfilEnum.superadministrador and not clube_atual
    if modo_plataforma:
        return {
            "dashboard_url": "/superadmin/clubes",
            "equipas": [],
            "pendencias": [],
            "total_pendencias": 0,
            "total_urgentes": 0,
            "acoes_rapidas": [],
            "notificacoes": [],
            "total_notificacoes": 0,
        }

    equipas = _equipas_permitidas(utilizador)
    equipa_ids = [equipa.id for equipa in equipas] if utilizador.perfil == PerfilEnum.treinador else None
    painel = obter_painel_operacional(
        db,
        equipa_ids=equipa_ids,
        perfil_visual=utilizador.perfil.value,
    )
    tarefas = painel.get("tarefas", [])
    if utilizador.perfil == PerfilEnum.secretaria:
        tarefas = [tarefa for tarefa in tarefas if _grupo_tarefa(tarefa) == "secretaria"]
    elif utilizador.perfil == PerfilEnum.coordenador:
        # A coordenação mantém acesso aos registos, sem os receber como pendências diárias.
        tarefas = [tarefa for tarefa in tarefas if _grupo_tarefa(tarefa) != "secretaria"]
    return {
        "dashboard_url": "/dashboard",
        "equipas": [{"id": equipa.id, "nome": equipa.nome} for equipa in equipas],
        "pendencias": _agrupar_pendencias(tarefas),
        "total_pendencias": len(tarefas),
        "total_urgentes": sum(1 for tarefa in tarefas if tarefa.get("urgente")),
        "acoes_rapidas": _acoes_rapidas(utilizador, equipas),
        "notificacoes": obter_notificacoes_utilizador(db, utilizador),
        "total_notificacoes": db.query(Notificacao).filter(
            Notificacao.utilizador_id == utilizador.id,
            Notificacao.lida.is_(False),
        ).count(),
    }

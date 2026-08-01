from datetime import datetime

from services.sessao_workflow import estado_sessao_visual, normalizar_estado_sessao, proxima_acao_sessao


def _pluralizar(numero: int, singular: str, plural: str) -> str:
    """Devolve a forma singular ou plural com base no número."""
    return singular if numero == 1 else plural


def formatar_data_hora(data_hora: datetime | None) -> str | None:
    """Formata data e hora num formato simples para apresentação."""
    if not data_hora:
        return None
    return data_hora.strftime("%d/%m/%Y %H:%M")


def construir_resumo_sincronizacao_texto(resumo: dict[str, int]) -> str:
    """Cria uma frase legível com o resultado da sincronização."""
    geradas = resumo.get("geradas", 0)
    atualizadas = resumo.get("atualizadas", 0)
    ignoradas_manuais = resumo.get("ignoradas_manuais", 0)
    inativadas = resumo.get("inativadas", 0)
    ignoradas = resumo.get("ignoradas", 0)
    sem_microciclo = resumo.get("sem_microciclo", 0)

    partes = [
        f"{geradas} {_pluralizar(geradas, 'sessão criada', 'sessões criadas')}",
        f"{atualizadas} {_pluralizar(atualizadas, 'sessão atualizada', 'sessões atualizadas')}",
        (
            f"{ignoradas_manuais} {_pluralizar(ignoradas_manuais, 'sessão ignorada por alteração manual', 'sessões ignoradas por alteração manual')}"
        ),
        f"{inativadas} {_pluralizar(inativadas, 'sessão desativada', 'sessões desativadas')}",
    ]

    if ignoradas:
        partes.append(f"{ignoradas} {_pluralizar(ignoradas, 'evento ignorado', 'eventos ignorados')}")
    if sem_microciclo:
        partes.append(
            f"{sem_microciclo} {_pluralizar(sem_microciclo, 'equipa sem microciclo compatível', 'equipas sem microciclo compatível')}"
        )

    if len(partes) == 1:
        corpo = partes[0]
    else:
        corpo = ", ".join(partes[:-1]) + f" e {partes[-1]}"
    return f"Sincronização concluída: {corpo}."


def obter_estado_visual_sessao(sessao) -> dict[str, str]:
    """Traduz o estado técnico da sessão para um estado visual simples."""
    if not sessao.ativa:
        return {
            "codigo": "desativada",
            "label": "Desativada",
            "classes": "bg-slate-200 text-slate-700",
        }

    if sessao.origem == "planeamento_global":
        if sessao.alterada_manual:
            return {
                "codigo": "alterada_manual",
                "label": "Alterada manualmente",
                "classes": "bg-amber-100 text-amber-800",
            }
        if sessao.sincronizada:
            return {
                "codigo": "sincronizada",
                "label": "Sincronizada",
                "classes": "bg-emerald-100 text-emerald-800",
            }
        return {
            "codigo": "desatualizada",
            "label": "Desatualizada",
            "classes": "bg-rose-100 text-rose-800",
        }

    return {
        "codigo": "manual",
        "label": "Manual",
        "classes": "bg-sky-100 text-sky-800",
    }


def obter_origem_visual_sessao(sessao) -> dict[str, str | None]:
    """Traduz a origem técnica da sessão para labels legíveis."""
    if sessao.origem == "planeamento_global":
        contexto = "Plano Semanal do Clube"
        if getattr(sessao, "plano_semanal_clube", None) and sessao.plano_semanal_clube.titulo:
            contexto = f"Plano Semanal do Clube: {sessao.plano_semanal_clube.titulo}"
        return {
            "label": "Planeamento Global do Clube",
            "classes": "bg-indigo-100 text-indigo-800",
            "contexto": contexto,
        }

    return {
        "label": "Manual da Equipa",
        "classes": "bg-slate-100 text-slate-700",
        "contexto": None,
    }


def enriquecer_sessao_para_ui(sessao):
    """Anexa metadados transitórios à sessão para simplificar os templates."""
    estado = obter_estado_visual_sessao(sessao)
    origem = obter_origem_visual_sessao(sessao)
    sessao.estado_visual_codigo = estado["codigo"]
    sessao.estado_visual_label = estado["label"]
    sessao.estado_visual_classes = estado["classes"]
    estado_operacional = estado_sessao_visual(getattr(sessao, "estado", None))
    sessao.estado_operacional = normalizar_estado_sessao(getattr(sessao, "estado", None))
    sessao.estado_operacional_visual_codigo = estado_operacional["codigo"]
    sessao.estado_operacional_visual_label = estado_operacional["label"]
    sessao.estado_operacional_visual_classes = estado_operacional["classes"]
    sessao.proxima_acao_operacional = proxima_acao_sessao(getattr(sessao, "estado", None))
    sessao.origem_visual_label = origem["label"]
    sessao.origem_visual_classes = origem["classes"]
    sessao.origem_visual_contexto = origem["contexto"]
    return sessao


def preparar_sessoes_para_ui(sessoes: list) -> list:
    """Aplica os metadados visuais a uma lista de sessões."""
    return [enriquecer_sessao_para_ui(sessao) for sessao in sessoes]


def sessao_corresponde_filtro(sessao, filtro: str) -> bool:
    """Valida se uma sessão deve aparecer num filtro visual simples."""
    if filtro == "manuais":
        return sessao.origem != "planeamento_global"
    if filtro == "planeamento_global":
        return sessao.origem == "planeamento_global"
    if filtro == "alteradas_manual":
        return sessao.alterada_manual is True
    if filtro == "desatualizadas":
        return (
            sessao.origem == "planeamento_global"
            and sessao.alterada_manual is False
            and sessao.sincronizada is False
            and sessao.ativa is True
        )
    return True

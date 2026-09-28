from __future__ import annotations

from collections import OrderedDict, defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import or_
from sqlalchemy.orm import Session

from models.jogo import Jogo
from models.planeamento import (
    ConteudoMapaAnual,
    ConteudoMapaAnualOculto,
    Macrociclo,
    Mesociclo,
    Microciclo,
    PlaneamentoAnualEquipa,
    PrioridadeConteudoMapaAnual,
)


MESES_PT = (
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
)

AREAS_MAPA = (
    ("Técnica Ofensiva", 10),
    ("Técnica Defensiva", 20),
    ("Tática Ofensiva", 30),
    ("Tática Defensiva", 40),
)


CATALOGO_PADRAO = (
    ("tecnica-ofensiva-passe-rececao", "Técnica Ofensiva", None, "Passe + receção", 10, 0, 10),
    ("tecnica-ofensiva-enquadramento", "Técnica Ofensiva", None, "Enquadramento", 10, 0, 20),
    ("tecnica-ofensiva-drible", "Técnica Ofensiva", None, "Drible", 10, 0, 30),
    ("tecnica-ofensiva-finalizacoes", "Técnica Ofensiva", None, "Finalizações diversas", 10, 0, 40),
    ("tecnica-ofensiva-3pts-drible", "Técnica Ofensiva", None, "3 pts. a partir do drible", 10, 0, 50),
    ("tecnica-ofensiva-3pts-rececao", "Técnica Ofensiva", None, "3 pts. a partir da receção", 10, 0, 60),
    ("tecnica-ofensiva-2pts-drible", "Técnica Ofensiva", None, "2 pts. a partir do drible", 10, 0, 70),
    ("tecnica-ofensiva-lance-livre", "Técnica Ofensiva", None, "Lance livre", 10, 0, 80),
    ("tecnica-defensiva-bola", "Técnica Defensiva", None, "Defesa da bola antes-durante-depois", 20, 0, 10),
    ("tecnica-defensiva-campo-inteiro", "Técnica Defensiva", None, "Defesa a campo inteiro", 20, 0, 20),
    ("tecnica-defensiva-close-out", "Técnica Defensiva", None, "Close-out", 20, 0, 30),
    ("tecnica-defensiva-linha-passe", "Técnica Defensiva", None, "Defesa da linha de passe", 20, 0, 40),
    ("tecnica-defensiva-cortes", "Técnica Defensiva", None, "Defesa dos cortes", 20, 0, 50),
    ("tatica-ofensiva-individual-vantagens", "Tática Ofensiva", "Individual ofensiva", "Vantagens numéricas", 30, 10, 10),
    ("tatica-ofensiva-individual-bd-drop", "Tática Ofensiva", "Individual ofensiva", "BD - Drop", 30, 10, 20),
    ("tatica-ofensiva-individual-bd-hard-show", "Tática Ofensiva", "Individual ofensiva", "BD - Hard Show", 30, 10, 30),
    ("tatica-ofensiva-individual-bd-push", "Tática Ofensiva", "Individual ofensiva", "BD - Push", 30, 10, 40),
    ("tatica-ofensiva-individual-bd-troca", "Tática Ofensiva", "Individual ofensiva", "BD - Troca", 30, 10, 50),
    ("tatica-ofensiva-coletiva-transicao", "Tática Ofensiva", "Coletiva ofensiva", "Transição ofensiva", 30, 20, 10),
    ("tatica-ofensiva-coletiva-reacoes", "Tática Ofensiva", "Coletiva ofensiva", "Reações", 30, 20, 20),
    ("tatica-ofensiva-coletiva-bola-dentro", "Tática Ofensiva", "Coletiva ofensiva", "Bola dentro", 30, 20, 30),
    ("tatica-ofensiva-coletiva-drag", "Tática Ofensiva", "Coletiva ofensiva", "1.º ou Drag", 30, 20, 40),
    ("tatica-ofensiva-coletiva-handoff", "Tática Ofensiva", "Coletiva ofensiva", "2.º Handoff", 30, 20, 50),
    ("tatica-ofensiva-coletiva-unselfish", "Tática Ofensiva", "Coletiva ofensiva", "2.º Unselfish", 30, 20, 60),
    ("tatica-defensiva-individual-bola", "Tática Defensiva", "Individual defensiva", "Defesa da bola", 40, 10, 10),
    ("tatica-defensiva-individual-sem-bola", "Tática Defensiva", "Individual defensiva", "Defesa do jogador sem bola", 40, 10, 20),
    ("tatica-defensiva-individual-bd-troca", "Tática Defensiva", "Individual defensiva", "BD - Troca", 40, 10, 30),
    ("tatica-defensiva-individual-bd-hard-show", "Tática Defensiva", "Individual defensiva", "BD - Hard Show", 40, 10, 40),
    ("tatica-defensiva-individual-bd-drop", "Tática Defensiva", "Individual defensiva", "BD - Drop", 40, 10, 50),
    ("tatica-defensiva-individual-bd-push", "Tática Defensiva", "Individual defensiva", "BD - Push", 40, 10, 60),
    ("tatica-defensiva-individual-bi-troca", "Tática Defensiva", "Individual defensiva", "BI - Troca", 40, 10, 70),
    ("tatica-defensiva-individual-bi-3", "Tática Defensiva", "Individual defensiva", "BI - 3.º", 40, 10, 80),
    ("tatica-defensiva-individual-bi-follow", "Tática Defensiva", "Individual defensiva", "BI - Follow", 40, 10, 90),
    ("tatica-defensiva-coletiva-ajudas", "Tática Defensiva", "Coletiva defensiva", "Sistemas de ajudas", 40, 20, 10),
    ("tatica-defensiva-coletiva-transicao", "Tática Defensiva", "Coletiva defensiva", "Transição defensiva", 40, 20, 20),
    ("tatica-defensiva-coletiva-press-hxh", "Tática Defensiva", "Coletiva defensiva", "Press HxH", 40, 20, 30),
    ("tatica-defensiva-coletiva-zona-press", "Tática Defensiva", "Coletiva defensiva", "Zona Press", 40, 20, 40),
    ("tatica-defensiva-coletiva-zona-23", "Tática Defensiva", "Coletiva defensiva", "Zona 2-3", 40, 20, 50),
    ("tatica-defensiva-coletiva-zona-131", "Tática Defensiva", "Coletiva defensiva", "Zona 1-3-1", 40, 20, 60),
)


def garantir_catalogo_padrao(db: Session, clube_id: int) -> None:
    existentes = {
        codigo for (codigo,) in db.query(ConteudoMapaAnual.codigo).filter(
            ConteudoMapaAnual.clube_id == clube_id,
        ).all()
    }
    agora = datetime.now()
    novos = [
        {
            "clube_id": clube_id,
            "codigo": codigo,
            "area": area,
            "subarea": subarea,
            "nome": nome,
            "ordem_area": ordem_area,
            "ordem_subarea": ordem_subarea,
            "ordem": ordem,
            "ativo": True,
            "criado_em": agora,
            "atualizado_em": agora,
        }
        for codigo, area, subarea, nome, ordem_area, ordem_subarea, ordem in CATALOGO_PADRAO
        if codigo not in existentes
    ]
    if not novos:
        return

    dialeto = db.get_bind().dialect.name
    if dialeto == "postgresql":
        from sqlalchemy.dialects.postgresql import insert

        instrucao = insert(ConteudoMapaAnual).values(novos).on_conflict_do_nothing(
            index_elements=["clube_id", "codigo"],
        )
        db.execute(instrucao)
    elif dialeto == "sqlite":
        from sqlalchemy.dialects.sqlite import insert

        instrucao = insert(ConteudoMapaAnual).values(novos).on_conflict_do_nothing(
            index_elements=["clube_id", "codigo"],
        )
        db.execute(instrucao)
    else:
        db.add_all(ConteudoMapaAnual(**dados) for dados in novos)
    db.flush()


def construir_semanas(data_inicio: date, data_fim: date) -> list[dict]:
    primeira = data_inicio - timedelta(days=data_inicio.weekday())
    ultima = data_fim + timedelta(days=6 - data_fim.weekday())
    semanas = []
    atual = primeira
    while atual <= ultima:
        fim = atual + timedelta(days=6)
        if atual <= data_inicio <= fim:
            referencia_mes = data_inicio
        elif atual <= data_fim <= fim:
            referencia_mes = data_fim
        else:
            referencia_mes = atual + timedelta(days=3)
        semanas.append({
            "indice": len(semanas),
            "inicio": atual,
            "fim": fim,
            "chave": atual.isoformat(),
            "numero": atual.isocalendar().week,
            "inicio_dia": atual.day,
            "fim_dia": fim.day,
            "mes_ano": (referencia_mes.year, referencia_mes.month),
        })
        atual += timedelta(days=7)
    return semanas


def _agrupar_meses(semanas: list[dict]) -> list[dict]:
    grupos = []
    for semana in semanas:
        chave = semana["mes_ano"]
        if not grupos or grupos[-1]["chave"] != chave:
            grupos.append({
                "chave": chave,
                "label": f"{MESES_PT[chave[1] - 1]} {chave[0]}",
                "span": 1,
            })
        else:
            grupos[-1]["span"] += 1
    return grupos


def _indice_semana(data_evento: date, semanas: list[dict]) -> int | None:
    if not semanas or data_evento < semanas[0]["inicio"] or data_evento > semanas[-1]["fim"]:
        return None
    return (data_evento - semanas[0]["inicio"]).days // 7


def _segmentos_ciclos(semanas: list[dict], ciclos: list, prefixo: str) -> list[dict]:
    valores = []
    for semana in semanas:
        # Pode haver ciclos em transição na mesma semana. O mapa tem de
        # mostrar todos, em vez de escolher apenas o primeiro e ocultar os
        # restantes (por exemplo, o Meso 2 quando o Meso 1 termina nessa semana).
        ciclos_na_semana = [
            item for item in ciclos
            if item.data_inicio <= semana["fim"] and item.data_fim >= semana["inicio"]
        ]
        valores.append({
            "ids": tuple(item.id for item in ciclos_na_semana),
            "ciclos": [
                {"id": item.id, "label": f"{prefixo} {item.numero}"}
                for item in ciclos_na_semana
            ],
        })

    segmentos = []
    for valor in valores:
        if segmentos and segmentos[-1]["ids"] == valor["ids"]:
            segmentos[-1]["span"] += 1
        else:
            segmentos.append({
                "ids": valor["ids"],
                "ciclos": valor["ciclos"],
                "label": " · ".join(item["label"] for item in valor["ciclos"]),
                "span": 1,
            })
    return segmentos


def _macrociclos_do_planeamento(db: Session, planeamento: PlaneamentoAnualEquipa) -> list[Macrociclo]:
    """Inclui ciclos da equipa no período, mesmo quando a ligação anual é legada."""
    return db.query(Macrociclo).filter(
        Macrociclo.equipa_id == planeamento.equipa_id,
        Macrociclo.data_inicio <= planeamento.data_fim,
        Macrociclo.data_fim >= planeamento.data_inicio,
    ).order_by(Macrociclo.data_inicio, Macrociclo.data_fim, Macrociclo.id).all()


def _microciclos_do_planeamento(db: Session, planeamento: PlaneamentoAnualEquipa) -> list[Microciclo]:
    """Devolve os microciclos atuais do anual, ordenados cronologicamente."""
    macros = _macrociclos_do_planeamento(db, planeamento)
    macro_ids = [item.id for item in macros]
    if not macro_ids:
        return []
    mesos = db.query(Mesociclo).filter(Mesociclo.macrociclo_id.in_(macro_ids)).order_by(
        Mesociclo.data_inicio, Mesociclo.data_fim, Mesociclo.id,
    ).all()
    meso_ids = [item.id for item in mesos]
    if not meso_ids:
        return []
    return db.query(Microciclo).filter(Microciclo.mesociclo_id.in_(meso_ids)).order_by(
        Microciclo.data_inicio, Microciclo.data_fim, Microciclo.id,
    ).all()


def sincronizar_prioridades_com_microciclos(db: Session, planeamento: PlaneamentoAnualEquipa) -> bool:
    """Religa prioridades às semanas dos microciclos atualmente existentes.

    A semana é a fonte de verdade. Uma prioridade definida antes de existir o
    microciclo é ligada automaticamente quando a estrutura é criada ou muda.
    """
    micros = _microciclos_do_planeamento(db, planeamento)
    micro_por_semana = {}
    for semana in construir_semanas(planeamento.data_inicio, planeamento.data_fim):
        micro = next(
            (item for item in micros if item.data_inicio <= semana["fim"] and item.data_fim >= semana["inicio"]),
            None,
        )
        micro_por_semana[semana["inicio"]] = micro.id if micro else None

    alterou = False
    for prioridade in db.query(PrioridadeConteudoMapaAnual).filter(
        PrioridadeConteudoMapaAnual.planeamento_anual_id == planeamento.id,
    ).all():
        micro_id = micro_por_semana.get(prioridade.semana_inicio)
        if prioridade.microciclo_id != micro_id:
            prioridade.microciclo_id = micro_id
            alterou = True
    return alterou


def obter_sugestoes_conteudos_microciclo(db: Session, microciclo: Microciclo) -> dict:
    """Prepara sugestões sucintas do mapa anual para a semana do microciclo."""
    anual = microciclo.mesociclo.macrociclo.planeamento_anual_equipa
    if not anual:
        return {"planeamento": None, "itens": [], "grupos": []}

    sincronizar_prioridades_com_microciclos(db, anual)
    semanas = {item["inicio"] for item in construir_semanas(microciclo.data_inicio, microciclo.data_fim)}
    ocultos = {
        conteudo_id for (conteudo_id,) in db.query(ConteudoMapaAnualOculto.conteudo_id).filter(
            ConteudoMapaAnualOculto.planeamento_anual_id == anual.id,
        ).all()
    }
    prioridades = db.query(PrioridadeConteudoMapaAnual).join(ConteudoMapaAnual).filter(
        PrioridadeConteudoMapaAnual.planeamento_anual_id == anual.id,
        PrioridadeConteudoMapaAnual.semana_inicio.in_(semanas),
        ConteudoMapaAnual.ativo.is_(True),
    ).order_by(
        PrioridadeConteudoMapaAnual.prioridade,
        ConteudoMapaAnual.ordem_area,
        ConteudoMapaAnual.ordem_subarea,
        ConteudoMapaAnual.ordem,
        ConteudoMapaAnual.nome,
    ).all()

    itens_por_conteudo = {}
    for prioridade in prioridades:
        conteudo = prioridade.conteudo
        if conteudo.id in ocultos:
            continue
        existente = itens_por_conteudo.get(conteudo.id)
        if not existente or prioridade.prioridade < existente["prioridade"]:
            itens_por_conteudo[conteudo.id] = {
                "nome": conteudo.nome,
                "area": conteudo.area,
                "subarea": conteudo.subarea,
                "prioridade": prioridade.prioridade,
            }

    itens = sorted(
        itens_por_conteudo.values(),
        key=lambda item: (item["prioridade"], item["area"], item["subarea"] or "", item["nome"]),
    )
    grupos_por_area = OrderedDict()
    for item in itens:
        grupo = grupos_por_area.setdefault(item["area"], {
            "nome": item["area"],
            "itens": [],
        })
        grupo["itens"].append(item)

    nomes_ordenados = [nome for nome, _ in AREAS_MAPA if nome in grupos_por_area]
    nomes_ordenados.extend(sorted(nome for nome in grupos_por_area if nome not in nomes_ordenados))
    grupos = []
    for nome_area in nomes_ordenados:
        grupo = grupos_por_area[nome_area]
        prioridades = [item["prioridade"] for item in grupo["itens"]]
        grupos.append({
            **grupo,
            "total": len(grupo["itens"]),
            "prioridade_principal": min(prioridades) if prioridades else None,
        })
    return {"planeamento": anual, "itens": itens, "grupos": grupos}


def _agrupar_catalogo(conteudos: list[ConteudoMapaAnual]) -> list[dict]:
    areas = OrderedDict()
    for conteudo in conteudos:
        area = areas.setdefault(conteudo.area, OrderedDict())
        area.setdefault(conteudo.subarea or "", []).append(conteudo)

    resultado = []
    for area_nome, subareas in areas.items():
        grupos = []
        total_area = 0
        for subarea_nome, itens in subareas.items():
            grupos.append({"nome": subarea_nome, "conteudos": itens, "total_linhas": len(itens)})
            total_area += len(itens)
        resultado.append({
            "nome": area_nome,
            "slug": area_nome.lower().replace(" ", "-"),
            "subareas": grupos,
            "total_linhas": total_area,
        })
    return resultado


def construir_mapa_conteudos(db: Session, planeamento: PlaneamentoAnualEquipa) -> dict:
    garantir_catalogo_padrao(db, planeamento.clube_id)
    semanas = construir_semanas(planeamento.data_inicio, planeamento.data_fim)

    conteudos_ocultos = {
        conteudo_id for (conteudo_id,) in db.query(ConteudoMapaAnualOculto.conteudo_id).filter(
            ConteudoMapaAnualOculto.planeamento_anual_id == planeamento.id,
        ).all()
    }
    consulta_conteudos = db.query(ConteudoMapaAnual).filter(
        ConteudoMapaAnual.clube_id == planeamento.clube_id,
        ConteudoMapaAnual.ativo.is_(True),
        or_(
            ConteudoMapaAnual.planeamento_anual_id.is_(None),
            ConteudoMapaAnual.planeamento_anual_id == planeamento.id,
        ),
    )
    if conteudos_ocultos:
        consulta_conteudos = consulta_conteudos.filter(ConteudoMapaAnual.id.notin_(conteudos_ocultos))
    conteudos = consulta_conteudos.order_by(
        ConteudoMapaAnual.ordem_area,
        ConteudoMapaAnual.ordem_subarea,
        ConteudoMapaAnual.ordem,
        ConteudoMapaAnual.nome,
    ).all()

    jogos_por_semana = defaultdict(list)
    jogos = db.query(Jogo).filter(
        Jogo.equipa_id == planeamento.equipa_id,
        Jogo.data >= semanas[0]["inicio"],
        Jogo.data <= semanas[-1]["fim"],
    ).order_by(Jogo.data, Jogo.hora, Jogo.id).all()
    for jogo in jogos:
        indice = _indice_semana(jogo.data, semanas)
        if indice is not None:
            jogos_por_semana[indice].append({
                "id": jogo.id,
                "adversario": jogo.adversario,
                "competicao": jogo.competicao or "",
                "casa_fora": "C" if jogo.em_casa else "F",
                "em_casa": jogo.em_casa,
            })

    macros = _macrociclos_do_planeamento(db, planeamento)
    macro_ids = [item.id for item in macros]
    mesos = db.query(Mesociclo).filter(Mesociclo.macrociclo_id.in_(macro_ids)).order_by(
        Mesociclo.data_inicio, Mesociclo.data_fim, Mesociclo.id,
    ).all() if macro_ids else []
    meso_ids = [item.id for item in mesos]
    micros = db.query(Microciclo).filter(Microciclo.mesociclo_id.in_(meso_ids)).order_by(
        Microciclo.data_inicio, Microciclo.data_fim, Microciclo.id,
    ).all() if meso_ids else []

    micro_por_semana = {}
    for semana in semanas:
        micro = next((item for item in micros if item.data_inicio <= semana["fim"] and item.data_fim >= semana["inicio"]), None)
        micro_por_semana[semana["chave"]] = micro.id if micro else None

    sincronizar_prioridades_com_microciclos(db, planeamento)
    prioridades_guardadas = db.query(PrioridadeConteudoMapaAnual).filter(
        PrioridadeConteudoMapaAnual.planeamento_anual_id == planeamento.id,
    ).all()
    matriz = defaultdict(dict)
    for item in prioridades_guardadas:
        matriz[item.conteudo_id][item.semana_inicio.isoformat()] = item.prioridade

    return {
        "semanas": semanas,
        "meses": _agrupar_meses(semanas),
        "areas": _agrupar_catalogo(conteudos),
        "jogos_por_semana": jogos_por_semana,
        "segmentos_macro": _segmentos_ciclos(semanas, macros, "Macro"),
        "segmentos_meso": _segmentos_ciclos(semanas, mesos, "Meso"),
        "segmentos_micro": _segmentos_ciclos(semanas, micros, "Micro"),
        "micro_por_semana": micro_por_semana,
        "prioridades": dict(matriz),
        "total_conteudos": len(conteudos),
        "conteudo_ids": {item.id for item in conteudos},
        "areas_disponiveis": [nome for nome, _ in AREAS_MAPA],
    }

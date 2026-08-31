from datetime import date

from database import SessionLocal
from models.atividade import Atividade
from models.equipa import Equipa, EscalaoEnum, GeneroEnum
from models.jogo import Jogo
from models.planeamento import Macrociclo, Mesociclo, Microciclo, SessaoTreino
from models.planeamento_clube import (
    EventoPlaneamentoClube,
    OrigemEventoPlaneamentoClubeEnum,
    TipoEventoPlaneamentoClubeEnum,
)
from services.planeamento_integrado_service import (
    _item_jogo,
    obter_dashboard_planeamento_anual,
    obter_dashboard_planeamento_equipa,
)


NOME_EQUIPA_TESTE = "Equipa Planeamento Integrado Pytest"
TITULO_ATIVIDADE_TESTE = "Atividade Planeamento Integrado Pytest"
TITULO_EVENTO_CLUBE_TESTE = "Evento Clube Planeamento Integrado Pytest"
TITULO_EVENTO_TREINO_TESTE = "Treino Global Planeamento Integrado Pytest"
ADVERSARIO_JOGO_TESTE = "Adversario Planeamento Integrado Pytest"


def test_itens_de_jogo_distinguem_casa_e_fora():
    equipa = Equipa(nome="Equipa de teste", escalao=EscalaoEnum.sub16, genero=GeneroEnum.feminino)
    jogo_casa = Jogo(
        data=date(2031, 8, 1), adversario="Casa", em_casa=True, equipa=equipa,
    )
    jogo_fora = Jogo(
        data=date(2031, 8, 2), adversario="Fora", em_casa=False, equipa=equipa,
    )

    item_casa = _item_jogo(jogo_casa)
    item_fora = _item_jogo(jogo_fora)

    assert item_casa["classe_jogo"] == "jogo-casa"
    assert item_casa["jogo_localidade"] == "Casa"
    assert "rose" in item_casa["card_classes"]
    assert item_fora["classe_jogo"] == "jogo-fora"
    assert item_fora["jogo_localidade"] == "Fora"
    assert "blue" in item_fora["card_classes"]


def _limpar_contexto_teste():
    db = SessionLocal()
    try:
        for sessao in db.query(SessaoTreino).all():
            if (
                sessao.microciclo
                and sessao.microciclo.mesociclo
                and sessao.microciclo.mesociclo.macrociclo
                and sessao.microciclo.mesociclo.macrociclo.equipa
                and sessao.microciclo.mesociclo.macrociclo.equipa.nome == NOME_EQUIPA_TESTE
            ):
                db.delete(sessao)

        for evento in db.query(EventoPlaneamentoClube).filter(
            EventoPlaneamentoClube.titulo.in_([
                TITULO_EVENTO_CLUBE_TESTE,
                TITULO_EVENTO_TREINO_TESTE,
            ])
        ).all():
            db.delete(evento)

        for jogo in db.query(Jogo).filter(Jogo.adversario == ADVERSARIO_JOGO_TESTE).all():
            db.delete(jogo)

        for atividade in db.query(Atividade).filter(Atividade.titulo == TITULO_ATIVIDADE_TESTE).all():
            db.delete(atividade)

        for micro in db.query(Microciclo).all():
            if micro.mesociclo and micro.mesociclo.macrociclo and micro.mesociclo.macrociclo.equipa and micro.mesociclo.macrociclo.equipa.nome == NOME_EQUIPA_TESTE:
                db.delete(micro)

        for meso in db.query(Mesociclo).all():
            if meso.macrociclo and meso.macrociclo.equipa and meso.macrociclo.equipa.nome == NOME_EQUIPA_TESTE:
                db.delete(meso)

        for macro in db.query(Macrociclo).all():
            if macro.equipa and macro.equipa.nome == NOME_EQUIPA_TESTE:
                db.delete(macro)

        for equipa in db.query(Equipa).filter(Equipa.nome == NOME_EQUIPA_TESTE).all():
            db.delete(equipa)

        db.commit()
    finally:
        db.close()


def test_dashboard_planeamento_integrado_agrega_fontes():
    _limpar_contexto_teste()
    db = SessionLocal()

    try:
        equipa = Equipa(
            nome=NOME_EQUIPA_TESTE,
            escalao=EscalaoEnum.sub16,
            genero=GeneroEnum.feminino,
        )
        db.add(equipa)
        db.flush()

        macro = Macrociclo(
            numero=1,
            data_inicio=date.fromisoformat("2031-08-01"),
            data_fim=date.fromisoformat("2031-08-31"),
            equipa_id=equipa.id,
        )
        db.add(macro)
        db.flush()

        meso = Mesociclo(
            numero=1,
            data_inicio=date.fromisoformat("2031-08-03"),
            data_fim=date.fromisoformat("2031-08-09"),
            macrociclo_id=macro.id,
        )
        db.add(meso)
        db.flush()

        micro = Microciclo(
            numero=1,
            data_inicio=date.fromisoformat("2031-08-03"),
            data_fim=date.fromisoformat("2031-08-09"),
            tipo="competitivo",
            mesociclo_id=meso.id,
        )
        db.add(micro)
        db.flush()

        sessao = SessaoTreino(
            data=date.fromisoformat("2031-08-04"),
            local="Pavilhao A",
            hora_inicio="18:00",
            hora_fim="19:30",
            volume_minutos=90,
            intensidade_rpe=7.0,
            e_jogo=False,
            numero_treino=1,
            origem="manual",
            sincronizada=False,
            alterada_manual=False,
            ativa=True,
            microciclo_id=micro.id,
        )
        db.add(sessao)

        jogo = Jogo(
            data=date.fromisoformat("2031-08-06"),
            hora="17:00",
            local="Pavilhao B",
            adversario=ADVERSARIO_JOGO_TESTE,
            competicao="Taca",
            em_casa=True,
            equipa_id=equipa.id,
        )
        db.add(jogo)

        atividade = Atividade(
            titulo=TITULO_ATIVIDADE_TESTE,
            data=date.fromisoformat("2031-08-07"),
            local="Sala de video",
            tipo="Formacao",
        )
        db.add(atividade)

        evento_clube = EventoPlaneamentoClube(
            tipo=TipoEventoPlaneamentoClubeEnum.evento_clube,
            titulo=TITULO_EVENTO_CLUBE_TESTE,
            descricao="Sessao de grupo",
            data=date.fromisoformat("2031-08-05"),
            hora_inicio="20:00",
            hora_fim="21:00",
            aplica_a_todas_equipas=True,
            origem=OrigemEventoPlaneamentoClubeEnum.manual,
        )
        db.add(evento_clube)

        evento_treino = EventoPlaneamentoClube(
            tipo=TipoEventoPlaneamentoClubeEnum.treino_equipa,
            titulo=TITULO_EVENTO_TREINO_TESTE,
            descricao="Treino global ainda nao sincronizado",
            data=date.fromisoformat("2031-08-03"),
            hora_inicio="19:00",
            hora_fim="20:30",
            equipa_id=equipa.id,
            origem=OrigemEventoPlaneamentoClubeEnum.manual,
        )
        db.add(evento_treino)

        db.commit()

        dashboard_equipa = obter_dashboard_planeamento_equipa(
            db,
            equipa.id,
            date.fromisoformat("2031-08-03"),
            date.fromisoformat("2031-08-09"),
        )
        dashboard_anual = obter_dashboard_planeamento_anual(
            db,
            date.fromisoformat("2031-08-01"),
            date.fromisoformat("2031-08-31"),
        )

        titulos = [item["titulo"] for item in dashboard_equipa["itens"]]

        assert dashboard_equipa["estatisticas"]["total_treinos"] == 2
        assert dashboard_equipa["estatisticas"]["total_jogos"] == 1
        assert dashboard_equipa["estatisticas"]["total_atividades"] == 2
        assert dashboard_equipa["estatisticas"]["total_itens"] == 5
        assert TITULO_EVENTO_TREINO_TESTE in titulos
        assert TITULO_EVENTO_CLUBE_TESTE in titulos
        assert TITULO_ATIVIDADE_TESTE in titulos
        assert any(item["titulo"] == f"vs {ADVERSARIO_JOGO_TESTE}" for item in dashboard_equipa["itens"])
        assert len(dashboard_equipa["dias"]) == 7
        assert dashboard_equipa["meses"][0]["estatisticas"]["itens"] == 5

        resumo_equipa = next(
            item for item in dashboard_anual["resumo_equipas"]
            if item["equipa"].nome == NOME_EQUIPA_TESTE
        )
        assert dashboard_anual["estatisticas"]["total_equipas"] >= 1
        assert resumo_equipa["total_macros"] == 1
        assert resumo_equipa["total_treinos"] == 1
        assert resumo_equipa["total_jogos"] == 1
    finally:
        db.close()
        _limpar_contexto_teste()

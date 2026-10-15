from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database import Base
from models.clube import Clube
from models.playbook import (
    CadernoPlaybook, JogadaCadernoPlaybook, PassoSetPlay, Playbook,
    SecaoCadernoPlaybook, SetPlay,
)
from models.scouting import ScoutingAdversario, ScoutingConceitoOfensivo, ScoutingMomentoPlaybook
from routers import scouting
from services.scouting_playbook_service import garantir_caderno_scouting


def _sessao():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[
        Clube.__table__, ScoutingAdversario.__table__, Playbook.__table__, SetPlay.__table__,
        PassoSetPlay.__table__, CadernoPlaybook.__table__, SecaoCadernoPlaybook.__table__,
        JogadaCadernoPlaybook.__table__, ScoutingConceitoOfensivo.__table__,
        ScoutingMomentoPlaybook.__table__,
    ])
    return Session(engine)


def _dados(db):
    adversario = ScoutingAdversario(clube_id=1, nome="Rivais BC", nome_normalizado="rivais bc")
    fonte = Playbook(clube_id=1, equipa_id=7, nome="Biblioteca")
    destino = Playbook(clube_id=1, equipa_id=7, nome="Scouting · Rivais BC")
    outra_equipa = Playbook(clube_id=1, equipa_id=8, nome="Outra equipa")
    db.add_all([adversario, fonte, destino, outra_equipa])
    db.flush()
    original = SetPlay(clube_id=1, playbook_id=fonte.id, nome="Horns", categoria="Ataque", descricao="Duas opções", ordem=0)
    alheia = SetPlay(clube_id=1, playbook_id=outra_equipa.id, nome="Outra", ordem=0)
    db.add_all([original, alheia])
    db.flush()
    db.add_all([
        PassoSetPlay(clube_id=1, setplay_id=original.id, ordem=0, observacao="Início", desenho='{"cena":1}', imagem_coach="data:image/png;base64,abc"),
        PassoSetPlay(clube_id=1, setplay_id=original.id, ordem=1, observacao="Bloqueio", desenho='{"cena":2}'),
        ScoutingConceitoOfensivo(clube_id=1, adversario_id=adversario.id, setplay_id=alheia.id, ordem=0),
    ])
    db.commit()
    return adversario, fonte, destino, original


def test_caderno_do_adversario_separa_conceitos_e_playbook_sem_cruzar_equipas():
    with _sessao() as db:
        adversario, _, destino, original = _dados(db)
        conceito = ScoutingConceitoOfensivo(clube_id=1, adversario_id=adversario.id, setplay_id=original.id, ordem=1)
        jogada = SetPlay(clube_id=1, playbook_id=destino.id, nome="Transição", ordem=0)
        db.add_all([conceito, jogada])
        db.flush()
        db.add(ScoutingMomentoPlaybook(clube_id=1, adversario_id=adversario.id, setplay_id=jogada.id, ordem=0))
        db.commit()

        caderno = garantir_caderno_scouting(db, adversario, 7)
        garantir_caderno_scouting(db, adversario, 7)
        db.commit()

        assert caderno.nome == "Rivais BC"
        assert {secao.nome for secao in caderno.secoes} == {"Playbook", "Conceitos"}
        assert {(entrada.setplay.nome, entrada.secao.nome) for entrada in caderno.jogadas} == {
            ("Horns", "Conceitos"), ("Transição", "Playbook"),
        }
        assert db.query(CadernoPlaybook).count() == 1
        assert db.query(JogadaCadernoPlaybook).count() == 2


def test_importacao_e_copia_preservam_todas_as_cenas(monkeypatch):
    with _sessao() as db:
        adversario, _, destino, original = _dados(db)
        monkeypatch.setattr(scouting, "_adversario_acessivel", lambda *_: adversario)
        monkeypatch.setattr(scouting, "equipa_id_adversario", lambda *_: 7)
        monkeypatch.setattr(scouting, "_playbook_scouting", lambda *_: destino)
        request = SimpleNamespace(session={})

        alheia = db.query(SetPlay).filter(SetPlay.nome == "Outra").one()
        resposta = scouting.importar_jogadas_coletivas(adversario.id, request, db, None, [original.id, alheia.id])
        assert resposta.status_code == 303
        momento = db.query(ScoutingMomentoPlaybook).filter(ScoutingMomentoPlaybook.adversario_id == adversario.id).one()
        assert momento.setplay.categoria == "Ataque"
        assert [(passo.ordem, passo.observacao, passo.desenho, passo.imagem_coach) for passo in momento.setplay.passos] == [
            (passo.ordem, passo.observacao, passo.desenho, passo.imagem_coach) for passo in original.passos
        ]

        resposta = scouting.copiar_elemento_desenhado("momento", momento.id, request, db, None)
        assert resposta.status_code == 303
        conceito = db.query(ScoutingConceitoOfensivo).join(SetPlay).filter(
            ScoutingConceitoOfensivo.adversario_id == adversario.id,
            SetPlay.playbook_id == destino.id,
        ).one()
        assert conceito.setplay_id != momento.setplay_id
        assert [passo.desenho for passo in conceito.setplay.passos] == [passo.desenho for passo in original.passos]
        assert {(entrada.setplay_id, entrada.secao.nome) for entrada in db.query(JogadaCadernoPlaybook).all()} == {
            (momento.setplay_id, "Playbook"), (conceito.setplay_id, "Conceitos"),
        }

        resposta = scouting.copiar_elemento_desenhado("conceito", conceito.id, request, db, None)
        assert resposta.status_code == 303
        assert db.query(ScoutingMomentoPlaybook).filter(ScoutingMomentoPlaybook.adversario_id == adversario.id).count() == 2
        assert db.query(JogadaCadernoPlaybook).count() == 3

        copia_final = db.query(ScoutingMomentoPlaybook).filter(
            ScoutingMomentoPlaybook.adversario_id == adversario.id,
            ScoutingMomentoPlaybook.setplay_id != momento.setplay_id,
        ).one()
        setplay_removido = copia_final.setplay_id
        scouting.eliminar_elemento_desenhado("momento", copia_final.id, request, db, None)
        assert db.query(JogadaCadernoPlaybook).filter(JogadaCadernoPlaybook.setplay_id == setplay_removido).count() == 0
        assert db.query(SetPlay).filter(SetPlay.id == setplay_removido).count() == 0

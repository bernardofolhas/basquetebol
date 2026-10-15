"""Organizacao e copias independentes das jogadas do scouting coletivo."""

from sqlalchemy.orm import Session

from models.playbook import (
    CadernoPlaybook, JogadaCadernoPlaybook, PassoSetPlay, Playbook,
    SecaoCadernoPlaybook, SetPlay,
)
from models.scouting import ScoutingAdversario, ScoutingConceitoOfensivo, ScoutingMomentoPlaybook


SECOES = {"momento": ("Playbook", 0), "conceito": ("Conceitos", 1)}


def equipa_id_adversario(adversario: ScoutingAdversario) -> int | None:
    ligacao = next((item for item in adversario.jogos if item.jogo and item.jogo.equipa_id), None)
    return ligacao.jogo.equipa_id if ligacao else None


def garantir_caderno_scouting(db: Session, adversario: ScoutingAdversario, equipa_id: int) -> CadernoPlaybook:
    """Cria as duas secções e recupera jogadas antigas ainda fora do caderno."""
    caderno = db.query(CadernoPlaybook).filter(
        CadernoPlaybook.equipa_id == equipa_id,
        CadernoPlaybook.scouting_adversario_id == adversario.id,
    ).first()
    if not caderno:
        caderno = CadernoPlaybook(
            clube_id=adversario.clube_id, equipa_id=equipa_id,
            scouting_adversario_id=adversario.id, nome=adversario.nome,
            descricao="Jogadas e conceitos do scouting coletivo.",
            ordem=db.query(CadernoPlaybook).filter(CadernoPlaybook.equipa_id == equipa_id).count(),
        )
        db.add(caderno)
        db.flush()
    elif caderno.nome != adversario.nome:
        caderno.nome = adversario.nome

    secoes = {secao.nome: secao for secao in db.query(SecaoCadernoPlaybook).filter(
        SecaoCadernoPlaybook.caderno_id == caderno.id,
    ).all()}
    for nome, ordem in SECOES.values():
        if nome not in secoes:
            secao = SecaoCadernoPlaybook(clube_id=adversario.clube_id, caderno_id=caderno.id, nome=nome, ordem=ordem)
            db.add(secao)
            db.flush()
            secoes[nome] = secao

    for modelo, tipo in ((ScoutingMomentoPlaybook, "momento"), (ScoutingConceitoOfensivo, "conceito")):
        ligados = db.query(modelo).join(SetPlay).join(Playbook).filter(
            modelo.adversario_id == adversario.id,
            Playbook.equipa_id == equipa_id,
        ).order_by(modelo.ordem, modelo.id).all()
        for ligado in ligados:
            if ligado.setplay_id:
                associar_ao_caderno(db, caderno, secoes[SECOES[tipo][0]], ligado.setplay_id)
    return caderno


def associar_ao_caderno(db: Session, caderno: CadernoPlaybook, secao: SecaoCadernoPlaybook, setplay_id: int) -> None:
    entrada = db.query(JogadaCadernoPlaybook).filter(
        JogadaCadernoPlaybook.caderno_id == caderno.id,
        JogadaCadernoPlaybook.setplay_id == setplay_id,
    ).first()
    if entrada:
        if entrada.secao_id != secao.id:
            entrada.secao_id = secao.id
            entrada.ordem = db.query(JogadaCadernoPlaybook).filter(JogadaCadernoPlaybook.secao_id == secao.id).count()
        return
    ordem = db.query(JogadaCadernoPlaybook).filter(JogadaCadernoPlaybook.secao_id == secao.id).count()
    db.add(JogadaCadernoPlaybook(
        clube_id=caderno.clube_id, caderno_id=caderno.id,
        secao_id=secao.id, setplay_id=setplay_id, ordem=ordem,
    ))


def copiar_setplay_completo(db: Session, origem: SetPlay, destino: Playbook, categoria: str) -> SetPlay:
    """Copia todos os passos, incluindo estado vetorial, imagens e observacoes."""
    copia = SetPlay(
        clube_id=destino.clube_id, playbook_id=destino.id, nome=origem.nome,
        categoria=categoria, descricao=origem.descricao, origem="scouting",
        ordem=db.query(SetPlay).filter(SetPlay.playbook_id == destino.id).count(),
    )
    db.add(copia)
    db.flush()
    for passo in sorted(origem.passos, key=lambda item: (item.ordem, item.id)):
        db.add(PassoSetPlay(
            clube_id=destino.clube_id, setplay_id=copia.id, ordem=passo.ordem,
            observacao=passo.observacao, desenho=passo.desenho, imagem_coach=passo.imagem_coach,
        ))
    return copia

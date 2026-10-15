from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import backref, relationship

from database import Base


class Playbook(Base):
    __tablename__ = "playbooks"
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False, index=True)

    id = Column(Integer, primary_key=True, index=True)
    equipa_id = Column(Integer, ForeignKey("equipas.id"), nullable=False)
    nome = Column(String, nullable=False)
    descricao = Column(Text, nullable=True)
    criado_em = Column(DateTime, default=datetime.now, nullable=False)
    atualizado_em = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)

    equipa = relationship("Equipa", backref="playbooks")
    setplays = relationship("SetPlay", back_populates="playbook", cascade="all, delete", order_by="SetPlay.ordem")


class CadernoPlaybook(Base):
    """Coleção editorial de jogadas da biblioteca de uma equipa."""

    __tablename__ = "cadernos_playbook"
    __table_args__ = (UniqueConstraint("equipa_id", "scouting_adversario_id", name="uq_caderno_scouting_equipa_adversario"),)
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False, index=True)

    id = Column(Integer, primary_key=True, index=True)
    equipa_id = Column(Integer, ForeignKey("equipas.id", ondelete="CASCADE"), nullable=False, index=True)
    scouting_adversario_id = Column(Integer, ForeignKey("scouting_adversarios.id", ondelete="SET NULL"), nullable=True, index=True)
    nome = Column(String, nullable=False)
    descricao = Column(Text, nullable=True)
    ordem = Column(Integer, nullable=False, default=0)
    criado_em = Column(DateTime, default=datetime.now, nullable=False)
    atualizado_em = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)

    equipa = relationship("Equipa", backref="cadernos_playbook")
    secoes = relationship(
        "SecaoCadernoPlaybook",
        back_populates="caderno",
        cascade="all, delete-orphan",
        order_by="SecaoCadernoPlaybook.ordem",
    )
    jogadas = relationship(
        "JogadaCadernoPlaybook",
        back_populates="caderno",
        cascade="all, delete-orphan",
        order_by="JogadaCadernoPlaybook.ordem",
    )


class SecaoCadernoPlaybook(Base):
    __tablename__ = "secoes_caderno_playbook"
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False, index=True)

    id = Column(Integer, primary_key=True, index=True)
    caderno_id = Column(Integer, ForeignKey("cadernos_playbook.id", ondelete="CASCADE"), nullable=False, index=True)
    nome = Column(String, nullable=False)
    ordem = Column(Integer, nullable=False, default=0)

    caderno = relationship("CadernoPlaybook", back_populates="secoes")
    jogadas = relationship("JogadaCadernoPlaybook", back_populates="secao", order_by="JogadaCadernoPlaybook.ordem")


class JogadaCadernoPlaybook(Base):
    __tablename__ = "jogadas_caderno_playbook"
    __table_args__ = (UniqueConstraint("caderno_id", "setplay_id", name="uq_jogada_caderno_setplay"),)
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False, index=True)

    id = Column(Integer, primary_key=True, index=True)
    caderno_id = Column(Integer, ForeignKey("cadernos_playbook.id", ondelete="CASCADE"), nullable=False, index=True)
    secao_id = Column(Integer, ForeignKey("secoes_caderno_playbook.id", ondelete="SET NULL"), nullable=True, index=True)
    setplay_id = Column(Integer, ForeignKey("setplays.id", ondelete="CASCADE"), nullable=False, index=True)
    ordem = Column(Integer, nullable=False, default=0)

    caderno = relationship("CadernoPlaybook", back_populates="jogadas")
    secao = relationship("SecaoCadernoPlaybook", back_populates="jogadas")
    setplay = relationship(
        "SetPlay",
        backref=backref("entradas_caderno", passive_deletes=True),
    )


class SetPlay(Base):
    __tablename__ = "setplays"
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False, index=True)

    id = Column(Integer, primary_key=True, index=True)
    playbook_id = Column(Integer, ForeignKey("playbooks.id"), nullable=False)
    nome = Column(String, nullable=False)
    categoria = Column(String, nullable=True)   # Ataque, Defesa, Transição, Zona, Bola parada
    descricao = Column(Text, nullable=True)
    origem = Column(String, nullable=False, default="manual")
    ordem = Column(Integer, nullable=False, default=0)
    criado_em = Column(DateTime, default=datetime.now, nullable=False)

    playbook = relationship("Playbook", back_populates="setplays")
    passos = relationship("PassoSetPlay", back_populates="setplay", cascade="all, delete", order_by="PassoSetPlay.ordem")


class PassoSetPlay(Base):
    __tablename__ = "passos_setplay"
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False, index=True)

    id = Column(Integer, primary_key=True, index=True)
    setplay_id = Column(Integer, ForeignKey("setplays.id"), nullable=False)
    ordem = Column(Integer, nullable=False, default=0)
    observacao = Column(Text, nullable=True)
    desenho = Column(Text, nullable=True)   # imagem e estado vetorial do desenho tático
    imagem_coach = Column(Text, nullable=True)  # fotografia/imagem alternativa otimizada

    setplay = relationship("SetPlay", back_populates="passos")

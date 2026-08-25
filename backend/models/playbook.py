from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

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


class SetPlay(Base):
    __tablename__ = "setplays"
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False, index=True)

    id = Column(Integer, primary_key=True, index=True)
    playbook_id = Column(Integer, ForeignKey("playbooks.id"), nullable=False)
    nome = Column(String, nullable=False)
    categoria = Column(String, nullable=True)   # Ataque, Defesa, Transição, Zona, Bola parada
    descricao = Column(Text, nullable=True)
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
    desenho = Column(Text, nullable=True)   # base64 PNG data URL
    imagem_coach = Column(Text, nullable=True)  # fotografia/imagem alternativa otimizada

    setplay = relationship("SetPlay", back_populates="passos")

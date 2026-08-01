import enum
from datetime import datetime

from sqlalchemy import Boolean, Column, Date, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from database import Base


class TipoEspacoTreinoEnum(str, enum.Enum):
    pavilhao = "pavilhao"
    meio_campo = "meio_campo"
    ginasio = "ginasio"
    outro = "outro"


class EspacoTreino(Base):
    __tablename__ = "espacos_treino"

    id = Column(Integer, primary_key=True, index=True)
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False, index=True)
    nome = Column(String, nullable=False)
    tipo = Column(Enum(TipoEspacoTreinoEnum), nullable=False)
    localizacao = Column(String, nullable=True)
    capacidade = Column(Integer, nullable=True)
    ativo = Column(Boolean, default=True, nullable=False)
    observacoes = Column(Text, nullable=True)
    criado_em = Column(DateTime, default=datetime.now, nullable=False)
    atualizado_em = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)

    atribuicoes_semanais = relationship(
        "AtribuicaoEspacoSemanal",
        back_populates="espaco",
        cascade="all, delete",
    )
    disponibilidades = relationship(
        "DisponibilidadeEspacoTreino",
        back_populates="espaco",
        cascade="all, delete-orphan",
        order_by="DisponibilidadeEspacoTreino.dia_semana, DisponibilidadeEspacoTreino.hora_inicio",
    )
    indisponibilidades = relationship(
        "IndisponibilidadeEspacoTreino",
        back_populates="espaco",
        cascade="all, delete-orphan",
        order_by="IndisponibilidadeEspacoTreino.data_inicio",
    )


class DisponibilidadeEspacoTreino(Base):
    __tablename__ = "disponibilidades_espaco_treino"

    id = Column(Integer, primary_key=True, index=True)
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="CASCADE"), nullable=False, index=True)
    espaco_id = Column(Integer, ForeignKey("espacos_treino.id", ondelete="CASCADE"), nullable=False, index=True)
    dia_semana = Column(Integer, nullable=False)
    hora_inicio = Column(String, nullable=False)
    hora_fim = Column(String, nullable=False)
    duracao_slot_minutos = Column(Integer, nullable=False, default=90)
    ativo = Column(Boolean, nullable=False, default=True)
    criado_em = Column(DateTime, default=datetime.now, nullable=False)

    espaco = relationship("EspacoTreino", back_populates="disponibilidades")


class IndisponibilidadeEspacoTreino(Base):
    __tablename__ = "indisponibilidades_espaco_treino"

    id = Column(Integer, primary_key=True, index=True)
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="CASCADE"), nullable=False, index=True)
    espaco_id = Column(Integer, ForeignKey("espacos_treino.id", ondelete="CASCADE"), nullable=False, index=True)
    data_inicio = Column(Date, nullable=False)
    data_fim = Column(Date, nullable=False)
    hora_inicio = Column(String, nullable=True)
    hora_fim = Column(String, nullable=True)
    motivo = Column(String, nullable=True)
    criado_em = Column(DateTime, default=datetime.now, nullable=False)

    espaco = relationship("EspacoTreino", back_populates="indisponibilidades")

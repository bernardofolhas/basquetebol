import enum
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, String, Text
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

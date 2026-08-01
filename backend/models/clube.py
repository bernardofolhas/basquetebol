import enum
from datetime import datetime

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from database import Base


class EstadoClubeEnum(str, enum.Enum):
    ativo = "ativo"
    suspenso = "suspenso"
    arquivado = "arquivado"


class Clube(Base):
    __tablename__ = "clubes"

    id = Column(Integer, primary_key=True, index=True)
    nome_oficial = Column(String, nullable=False)
    nome_curto = Column(String, nullable=False)
    identificador = Column(String, nullable=False, unique=True, index=True)
    logo_principal = Column(String, nullable=True)
    logo_secundario = Column(String, nullable=True)
    cor_principal = Column(String, nullable=False, default="#f97316")
    cor_secundaria = Column(String, nullable=False, default="#1f2937")
    cor_destaque = Column(String, nullable=False, default="#0ea5e9")
    tema_gerado = Column(Text, nullable=True)
    estado = Column(Enum(EstadoClubeEnum), nullable=False, default=EstadoClubeEnum.ativo)
    epoca_inicial = Column(String, nullable=True)
    administrador_principal_id = Column(
        Integer, ForeignKey("utilizadores.id", ondelete="SET NULL"), nullable=True
    )
    criado_em = Column(DateTime, nullable=False, default=datetime.now)
    atualizado_em = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    administrador_principal = relationship("Utilizador", foreign_keys=[administrador_principal_id])

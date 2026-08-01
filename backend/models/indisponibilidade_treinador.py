from datetime import datetime

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from database import Base


class IndisponibilidadeTreinador(Base):
    __tablename__ = "indisponibilidades_treinador"

    id = Column(Integer, primary_key=True, index=True)
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="CASCADE"), nullable=False, index=True)
    treinador_id = Column(Integer, ForeignKey("treinadores.id", ondelete="CASCADE"), nullable=False, index=True)
    data = Column(Date, nullable=False, index=True)
    hora_inicio = Column(String, nullable=False)
    hora_fim = Column(String, nullable=False)
    motivo = Column(String, nullable=True)
    criado_em = Column(DateTime, nullable=False, default=datetime.now)

    treinador = relationship("Treinador", backref="indisponibilidades_planeamento")

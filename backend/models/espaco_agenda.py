from datetime import datetime

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from database import Base


class AgendaEspacoEquipa(Base):
    """Atribuição direta de espaço de treino a uma equipa numa data e horário específicos."""
    __tablename__ = "agenda_espaco_equipa"
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False, index=True)

    id = Column(Integer, primary_key=True, index=True)
    espaco_id = Column(Integer, ForeignKey("espacos_treino.id", ondelete="CASCADE"), nullable=False)
    equipa_id = Column(Integer, ForeignKey("equipas.id", ondelete="CASCADE"), nullable=False)
    data = Column(Date, nullable=False, index=True)
    hora_inicio = Column(String(5), nullable=False)
    hora_fim = Column(String(5), nullable=False)
    observacoes = Column(Text, nullable=True)
    ativo = Column(Boolean, default=True, nullable=False)
    criado_em = Column(DateTime, default=datetime.now, nullable=False)

    espaco = relationship("EspacoTreino", backref="agenda_equipas")
    equipa = relationship("Equipa", backref="agenda_espacos")

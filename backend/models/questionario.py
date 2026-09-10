from datetime import date, datetime

from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from database import Base


class RespostaQuestionarioDiario(Base):
    __tablename__ = "respostas_questionario_diario"

    id = Column(Integer, primary_key=True, index=True)
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False, index=True)
    jogador_id = Column(Integer, ForeignKey("jogadores.id", ondelete="CASCADE"), nullable=False, index=True)
    data = Column(Date, nullable=False, default=date.today, index=True)
    tipo_sessao = Column(String, nullable=False)
    horas_sono = Column(Float, nullable=True)
    qualidade_sono = Column(Integer, nullable=False)
    pse_esforco = Column(Integer, nullable=False)
    dor_membros_inferiores = Column(Integer, nullable=False)
    dor_membros_superiores = Column(Integer, nullable=False)
    tem_queixa = Column(Boolean, nullable=False, default=False)
    descricao_queixa = Column(Text, nullable=True)
    observacoes = Column(Text, nullable=True)
    criado_em = Column(DateTime, nullable=False, default=datetime.now)
    atualizado_em = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    jogador = relationship("Jogador", backref="respostas_questionario_diario")

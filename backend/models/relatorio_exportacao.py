from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from database import Base


class PredefinicaoRelatorio(Base):
    __tablename__ = "predefinicoes_relatorios"
    __table_args__ = (
        UniqueConstraint("clube_id", "tipo", "ambito", "utilizador_id", "equipa_id", "nome", name="uq_predefinicao_relatorio_contexto"),
    )

    id = Column(Integer, primary_key=True)
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="CASCADE"), nullable=False, index=True)
    utilizador_id = Column(Integer, ForeignKey("utilizadores.id", ondelete="CASCADE"), nullable=True, index=True)
    equipa_id = Column(Integer, ForeignKey("equipas.id", ondelete="CASCADE"), nullable=True, index=True)
    tipo = Column(String(32), nullable=False, index=True)
    ambito = Column(String(16), nullable=False, default="pessoal")
    nome = Column(String(120), nullable=False)
    formato = Column(String(24), nullable=False, default="completo")
    orientacao = Column(String(16), nullable=False, default="retrato")
    secoes = Column(Text, nullable=False)
    configuracao = Column(Text, nullable=True)
    protegido = Column(Boolean, nullable=False, default=False)
    criado_em = Column(DateTime, nullable=False, default=datetime.now)
    atualizado_em = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    utilizador = relationship("Utilizador")
    equipa = relationship("Equipa")

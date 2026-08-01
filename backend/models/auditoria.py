from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from database import Base


class RegistoAuditoria(Base):
    """Rasto mínimo de alterações relevantes para administração e suporte."""

    __tablename__ = "registos_auditoria"

    id = Column(Integer, primary_key=True, index=True)
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="SET NULL"), nullable=True, index=True)
    criado_em = Column(DateTime, default=datetime.now, nullable=False, index=True)
    utilizador_id = Column(Integer, ForeignKey("utilizadores.id", ondelete="SET NULL"), nullable=True)
    utilizador_username = Column(String, nullable=True)
    acao = Column(String, nullable=False)
    entidade = Column(String, nullable=False)
    entidade_id = Column(Integer, nullable=True)
    detalhes = Column(Text, nullable=True)
    endereco_ip = Column(String, nullable=True)

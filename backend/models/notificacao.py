from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text

from database import Base


class Notificacao(Base):
    """Mensagem operacional privada apresentada na barra global do utilizador."""

    __tablename__ = "notificacoes"

    id = Column(Integer, primary_key=True, index=True)
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False, index=True)
    utilizador_id = Column(Integer, ForeignKey("utilizadores.id", ondelete="CASCADE"), nullable=False, index=True)
    titulo = Column(String, nullable=False)
    mensagem = Column(Text, nullable=False)
    link = Column(String, nullable=True)
    lida = Column(Boolean, nullable=False, default=False)
    criado_em = Column(DateTime, nullable=False, default=datetime.now)

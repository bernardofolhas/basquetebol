from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from database import Base


class HistoricoPlaneamentoClube(Base):
    """Histórico funcional de publicação, sincronização e edição do planeamento."""

    __tablename__ = "historico_planeamento_clube"

    id = Column(Integer, primary_key=True, index=True)
    criado_em = Column(DateTime, default=datetime.now, nullable=False, index=True)
    utilizador_id = Column(Integer, ForeignKey("utilizadores.id", ondelete="SET NULL"), nullable=True)
    utilizador_username = Column(String, nullable=True)
    entidade = Column(String, nullable=False)
    entidade_id = Column(Integer, nullable=False)
    acao = Column(String, nullable=False)
    detalhes = Column(Text, nullable=True)

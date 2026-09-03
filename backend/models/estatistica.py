from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import backref, relationship

from database import Base


class EventoEstatistica(Base):
    """Ação atómica de um jogo, sincronizável e anulável sem perder histórico."""

    __tablename__ = "eventos_estatistica"

    id = Column(Integer, primary_key=True, index=True)
    client_uid = Column(String(80), nullable=False, unique=True, index=True)
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="CASCADE"), nullable=False, index=True)
    equipa_id = Column(Integer, ForeignKey("equipas.id", ondelete="CASCADE"), nullable=False, index=True)
    jogo_id = Column(Integer, ForeignKey("jogos.id", ondelete="CASCADE"), nullable=False, index=True)
    jogador_id = Column(Integer, ForeignKey("jogadores.id", ondelete="SET NULL"), nullable=True, index=True)
    registado_por_id = Column(Integer, ForeignKey("utilizadores.id", ondelete="SET NULL"), nullable=True)
    lado = Column(String(16), nullable=False, default="equipa", server_default="equipa")
    tipo = Column(String(32), nullable=False, index=True)
    periodo = Column(Integer, nullable=False, default=1, server_default="1")
    segundos_restantes = Column(Integer, nullable=True)
    posicao_x = Column(Float, nullable=True)
    posicao_y = Column(Float, nullable=True)
    anulado = Column(Boolean, nullable=False, default=False, server_default="false")
    criado_em = Column(DateTime, nullable=False, default=datetime.now)
    atualizado_em = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    jogo = relationship(
        "Jogo",
        backref=backref("eventos_estatistica", cascade="all, delete-orphan", passive_deletes=True),
    )
    jogador = relationship("Jogador")
    registado_por = relationship("Utilizador")

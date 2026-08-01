from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import backref, relationship

from database import Base


class TokenRecuperacaoPassword(Base):
    __tablename__ = "tokens_recuperacao_password"

    id = Column(Integer, primary_key=True, index=True)
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="CASCADE"), nullable=True, index=True)
    utilizador_id = Column(Integer, ForeignKey("utilizadores.id", ondelete="CASCADE"), nullable=False, index=True)
    criado_por_id = Column(Integer, ForeignKey("utilizadores.id", ondelete="SET NULL"), nullable=True)
    token_hash = Column(String(64), nullable=False, unique=True, index=True)
    tipo = Column(String, nullable=False, default="email")
    criado_em = Column(DateTime, default=datetime.now, nullable=False)
    expira_em = Column(DateTime, nullable=False, index=True)
    utilizado_em = Column(DateTime, nullable=True)
    pedido_ip = Column(String, nullable=True)

    utilizador = relationship(
        "Utilizador",
        foreign_keys=[utilizador_id],
        backref=backref("tokens_recuperacao", cascade="all, delete", passive_deletes=True),
    )
    criado_por = relationship("Utilizador", foreign_keys=[criado_por_id])

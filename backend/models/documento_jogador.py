from datetime import datetime

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import backref, relationship

from database import Base


class DocumentoJogador(Base):
    """Documento administrativo associado ao processo de uma jogadora."""

    __tablename__ = "documentos_jogadores"
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False, index=True)

    id = Column(Integer, primary_key=True, index=True)
    jogador_id = Column(Integer, ForeignKey("jogadores.id", ondelete="CASCADE"), nullable=False)
    tipo = Column(String, nullable=False)
    nome = Column(String, nullable=False)
    data_documento = Column(Date, nullable=True)
    validade = Column(Date, nullable=True)
    estado = Column(String, nullable=False, default="pendente", server_default="pendente")
    observacoes = Column(Text, nullable=True)
    criado_em = Column(DateTime, default=datetime.now, nullable=False)
    atualizado_em = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)

    jogador = relationship(
        "Jogador",
        backref=backref("documentos", cascade="all, delete-orphan", passive_deletes=True),
    )

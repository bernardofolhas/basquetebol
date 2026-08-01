from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from database import Base


class IdentidadeClube(Base):
    """Configuração visual única do clube usada na aplicação e nos PDFs."""

    __tablename__ = "identidade_clube"

    id = Column(Integer, primary_key=True, index=True)
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    nome_oficial = Column(String, nullable=False, default="Clube de Basquetebol")
    nome_curto = Column(String, nullable=True)
    logo_principal = Column(String, nullable=True)
    logo_secundario = Column(String, nullable=True)
    cor_principal = Column(String, nullable=False, default="#f97316")
    cor_secundaria = Column(String, nullable=False, default="#1f2937")
    cor_destaque = Column(String, nullable=False, default="#0ea5e9")
    texto_rodape = Column(Text, nullable=True)
    epoca_predefinida = Column(String, nullable=True)
    criado_em = Column(DateTime, nullable=False, default=datetime.now)
    atualizado_em = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

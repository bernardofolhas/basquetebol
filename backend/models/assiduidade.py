# ─────────────────────────────────────────────────────────────
# MODELO DE ASSIDUIDADE
# Regista a presença de cada jogador em cada sessão de treino
# ─────────────────────────────────────────────────────────────

from sqlalchemy import Column, Integer, Boolean, String, ForeignKey
from sqlalchemy.orm import backref, relationship
from database import Base


class RegistoAssiduidade(Base):
    __tablename__ = "assiduidade"
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False, index=True)

    id = Column(Integer, primary_key=True, index=True)

    # ForeignKey aponta para a coluna 'id' da tabela 'sessoes_treino'
    sessao_id = Column(Integer, ForeignKey("sessoes_treino.id", ondelete="CASCADE"), nullable=False)

    # Ligação ao jogador
    jogador_id = Column(Integer, ForeignKey("jogadores.id", ondelete="CASCADE"), nullable=False)

    # True = presente, False = ausente. Mantido por compatibilidade.
    presente = Column(Boolean, nullable=False, default=False)

    # Detalhe operacional do registo (o booleano antigo continua disponível).
    estado = Column(String, nullable=False, default="ausente", server_default="ausente")

    # Motivo da falta — só relevante quando presente=False
    motivo_falta = Column(String, nullable=True)

    # relationship permite aceder aos dados relacionados directamente
    sessao = relationship(
        "SessaoTreino",
        backref=backref("registos_assiduidade", cascade="all, delete-orphan"),
    )
    jogador = relationship(
        "Jogador",
        backref=backref("registos_assiduidade", cascade="all, delete-orphan"),
    )

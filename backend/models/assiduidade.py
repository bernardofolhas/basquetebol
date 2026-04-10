# ─────────────────────────────────────────────────────────────
# MODELO DE ASSIDUIDADE
# Regista a presença de cada jogador em cada sessão de treino
# ─────────────────────────────────────────────────────────────

from sqlalchemy import Column, Integer, Boolean, String, ForeignKey
from sqlalchemy.orm import relationship
from database import Base


class RegistoAssiduidade(Base):
    __tablename__ = "assiduidade"

    id = Column(Integer, primary_key=True, index=True)

    # ForeignKey aponta para a coluna 'id' da tabela 'sessoes_treino'
    sessao_id = Column(Integer, ForeignKey("sessoes_treino.id"), nullable=False)

    # Ligação ao jogador
    jogador_id = Column(Integer, ForeignKey("jogadores.id"), nullable=False)

    # True = presente, False = ausente
    presente = Column(Boolean, default=False)

    # Motivo da falta — só relevante quando presente=False
    motivo_falta = Column(String, nullable=True)

    # relationship permite aceder aos dados relacionados directamente
    sessao = relationship("SessaoTreino", backref="registos_assiduidade")
    jogador = relationship("Jogador", backref="registos_assiduidade")
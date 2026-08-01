# ─────────────────────────────────────────────────────────────
# MODELO DE PREPARAÇÃO FÍSICA
# Testes de condição física e planeamento físico por equipa
# ─────────────────────────────────────────────────────────────

from sqlalchemy import Column, Integer, String, Date, Float, Text, ForeignKey
from sqlalchemy.orm import backref, relationship
from database import Base


class TesteFisico(Base):
    # Registo de um teste de condição física de um jogador
    __tablename__ = "testes_fisicos"
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False, index=True)

    id = Column(Integer, primary_key=True, index=True)

    # Data e tipo do teste
    data = Column(Date, nullable=False)
    tipo_teste = Column(String, nullable=False)  # Ex: "Yo-Yo", "Sprint 20m", "CMJ"

    # Resultado numérico e unidade
    resultado = Column(Float, nullable=True)      # Ex: 18.5
    unidade = Column(String, nullable=True)       # Ex: "nível", "segundos", "cm"

    # Observações
    observacoes = Column(Text, nullable=True)

    # Ligação ao jogador
    jogador_id = Column(Integer, ForeignKey("jogadores.id", ondelete="CASCADE"), nullable=False)
    jogador = relationship(
        "Jogador",
        backref=backref("testes_fisicos", cascade="all, delete-orphan", passive_deletes=True),
    )


class PlaneamentoFisico(Base):
    # Planeamento físico semanal/mensal de uma equipa
    __tablename__ = "planeamentos_fisicos"
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False, index=True)

    id = Column(Integer, primary_key=True, index=True)

    # Período do planeamento
    data_inicio = Column(Date, nullable=False)
    data_fim = Column(Date, nullable=False)
    tipo = Column(String, nullable=True)  # "Semanal" ou "Mensal"

    # Conteúdos físicos
    resistencia = Column(Text, nullable=True)
    velocidade = Column(Text, nullable=True)
    forca = Column(Text, nullable=True)
    flexibilidade = Column(Text, nullable=True)
    coordenacao = Column(Text, nullable=True)
    observacoes = Column(Text, nullable=True)

    # Ligação à equipa
    equipa_id = Column(Integer, ForeignKey("equipas.id"), nullable=False)
    equipa = relationship("Equipa", backref="planeamentos_fisicos")

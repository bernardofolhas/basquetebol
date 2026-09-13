# ─────────────────────────────────────────────────────────────
# MODELO DE PREPARAÇÃO FÍSICA
# Testes de condição física e planeamento físico por equipa
# ─────────────────────────────────────────────────────────────

from sqlalchemy import Boolean, Column, Integer, String, Date, Float, Text, ForeignKey
from sqlalchemy.orm import backref, relationship
from database import Base


class DefinicaoTesteFisico(Base):
    """Teste reutilizável disponível no catálogo do clube."""

    __tablename__ = "definicoes_testes_fisicos"

    id = Column(Integer, primary_key=True, index=True)
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="CASCADE"), nullable=False, index=True)
    nome = Column(String, nullable=False)
    lateralidade = Column(String, nullable=False, default="bilateral")
    unidade_total = Column(String, nullable=True)
    unidade_esquerda = Column(String, nullable=True)
    unidade_direita = Column(String, nullable=True)
    ativo = Column(Boolean, nullable=False, default=True)


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
    resultado_esquerdo = Column(Float, nullable=True)
    resultado_direito = Column(Float, nullable=True)
    unidade_esquerda = Column(String, nullable=True)
    unidade_direita = Column(String, nullable=True)
    assimetria_percentual = Column(Float, nullable=True)
    lateralidade = Column(String, nullable=False, default="bilateral")
    medicao_id = Column(String(36), nullable=True, index=True)
    definicao_id = Column(
        Integer,
        ForeignKey("definicoes_testes_fisicos.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    definicao = relationship("DefinicaoTesteFisico", backref="resultados")

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

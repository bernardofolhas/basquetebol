# ─────────────────────────────────────────────────────────────
# MODELO DE JOGO
# Representa um jogo oficial no calendário da equipa
# ─────────────────────────────────────────────────────────────

from sqlalchemy import Column, Integer, String, Date, Boolean, ForeignKey, Text
from sqlalchemy.orm import relationship
from database import Base


class Jogo(Base):
    __tablename__ = "jogos"

    id = Column(Integer, primary_key=True, index=True)

    # Informações básicas
    data = Column(Date, nullable=False)
    hora = Column(String, nullable=True)           # Ex: "15:00"
    local = Column(String, nullable=True)          # Pavilhão
    adversario = Column(String, nullable=False)    # Nome do adversário
    competicao = Column(String, nullable=True)     # Ex: "Campeonato Nacional"

    # Casa ou fora
    em_casa = Column(Boolean, default=True)

    # Resultado — preenchido após o jogo
    pontos_nos = Column(Integer, nullable=True)
    pontos_adversario = Column(Integer, nullable=True)

    # Observações gerais
    observacoes = Column(Text, nullable=True)

    # Ligação à equipa
    equipa_id = Column(Integer, ForeignKey("equipas.id"), nullable=False)
    equipa = relationship("Equipa", backref="jogos")

    # Convocados para este jogo
    convocados = relationship("Convocado", back_populates="jogo",
                              cascade="all, delete")


class Convocado(Base):
    # Jogador convocado para um jogo específico
    __tablename__ = "convocados"

    id = Column(Integer, primary_key=True, index=True)

    # Ligação ao jogo e ao jogador
    jogo_id = Column(Integer, ForeignKey("jogos.id"), nullable=False)
    jogador_id = Column(Integer, ForeignKey("jogadores.id"), nullable=False)

    # Informações da convocatória
    hora_encontro = Column(String, nullable=True)   # Ex: "14:00"
    local_encontro = Column(String, nullable=True)  # Ex: "Pavilhão Municipal"
    observacoes = Column(Text, nullable=True)       # Ex: "Trazer equipamento completo"

    # Relações
    jogo = relationship("Jogo", back_populates="convocados")
    jogador = relationship("Jogador")

class PlanoJogo(Base):
    __tablename__ = "planos_jogo"

    id = Column(Integer, primary_key=True, index=True)
    jogo_id = Column(Integer, ForeignKey("jogos.id"), nullable=False, unique=True)

    # 5 inicial
    titular_1 = Column(Integer, ForeignKey("jogadores.id"), nullable=True)
    titular_2 = Column(Integer, ForeignKey("jogadores.id"), nullable=True)
    titular_3 = Column(Integer, ForeignKey("jogadores.id"), nullable=True)
    titular_4 = Column(Integer, ForeignKey("jogadores.id"), nullable=True)
    titular_5 = Column(Integer, ForeignKey("jogadores.id"), nullable=True)
    rotacoes = Column(Text, nullable=True)

    # Chaves
    chaves_ataque = Column(Text, nullable=True)
    chaves_defesa = Column(Text, nullable=True)
    movimentos_ofensivos = Column(Text, nullable=True)

    # Estratégias defensivas
    bloqueio_direto_lateral = Column(Text, nullable=True)
    bloqueio_direto_central = Column(Text, nullable=True)
    handoff = Column(Text, nullable=True)
    indiretos_entrada = Column(Text, nullable=True)
    indiretos_saida = Column(Text, nullable=True)
    bola_dentro = Column(Text, nullable=True)
    situacoes_especiais = Column(Text, nullable=True)

    reflexao = Column(Text, nullable=True)

    jogo = relationship("Jogo", backref="plano_jogo", uselist=False)    
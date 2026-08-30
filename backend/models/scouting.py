"""Registos de scouting de adversários e auto-scouting, sempre ligados a um jogo."""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from database import Base


class RelatorioScouting(Base):
    __tablename__ = "relatorios_scouting"

    id = Column(Integer, primary_key=True, index=True)
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False, index=True)
    jogo_id = Column(Integer, ForeignKey("jogos.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    estado = Column(String(24), nullable=False, default="rascunho")
    jogos_observados = Column(String(120), nullable=True)
    fontes = Column(Text, nullable=True)
    confianca = Column(String(24), nullable=True)

    identidade = Column(Text, nullable=True)
    pontos_fortes = Column(Text, nullable=True)
    vulnerabilidades = Column(Text, nullable=True)
    ataque = Column(Text, nullable=True)
    defesa = Column(Text, nullable=True)
    transicao = Column(Text, nullable=True)
    situacoes_especiais = Column(Text, nullable=True)
    prioridades_defensivas = Column(Text, nullable=True)
    prioridades_ofensivas = Column(Text, nullable=True)
    primeiros_minutos = Column(Text, nullable=True)
    plano_contingencia = Column(Text, nullable=True)

    auto_scouting = Column(Text, nullable=True)
    melhorias_prioritarias = Column(Text, nullable=True)
    criado_em = Column(DateTime, nullable=False, default=datetime.now)
    atualizado_em = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)
    publicado_em = Column(DateTime, nullable=True)

    jogo = relationship("Jogo", back_populates="scouting")
    jogadores_adversarios = relationship(
        "ScoutingJogadorAdversario", back_populates="relatorio", cascade="all, delete-orphan", order_by="ScoutingJogadorAdversario.ordem"
    )
    acoes = relationship(
        "ScoutingAcao", back_populates="relatorio", cascade="all, delete-orphan", order_by="ScoutingAcao.ordem"
    )


class ScoutingJogadorAdversario(Base):
    __tablename__ = "scouting_jogadores_adversarios"

    id = Column(Integer, primary_key=True, index=True)
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False, index=True)
    relatorio_id = Column(Integer, ForeignKey("relatorios_scouting.id", ondelete="CASCADE"), nullable=False, index=True)
    ordem = Column(Integer, nullable=False, default=0)
    numero = Column(String(12), nullable=True)
    nome = Column(String(160), nullable=False)
    posicao = Column(String(48), nullable=True)
    papel = Column(String(100), nullable=True)
    mao_dominante = Column(String(24), nullable=True)
    como_pontua = Column(Text, nullable=True)
    tendencias = Column(Text, nullable=True)
    pontos_fortes = Column(Text, nullable=True)
    limitacoes = Column(Text, nullable=True)
    como_defender = Column(Text, nullable=True)
    como_atacar = Column(Text, nullable=True)
    prioridade = Column(Boolean, nullable=False, default=False)
    partilhavel = Column(Boolean, nullable=False, default=True)

    relatorio = relationship("RelatorioScouting", back_populates="jogadores_adversarios")


class ScoutingAcao(Base):
    __tablename__ = "scouting_acoes"

    id = Column(Integer, primary_key=True, index=True)
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False, index=True)
    relatorio_id = Column(Integer, ForeignKey("relatorios_scouting.id", ondelete="CASCADE"), nullable=False, index=True)
    ordem = Column(Integer, nullable=False, default=0)
    categoria = Column(String(64), nullable=False, default="Ataque")
    nome = Column(String(160), nullable=False)
    descricao = Column(Text, nullable=True)
    resposta = Column(Text, nullable=True)
    prioridade = Column(Boolean, nullable=False, default=False)
    partilhavel = Column(Boolean, nullable=False, default=True)

    relatorio = relationship("RelatorioScouting", back_populates="acoes")

from datetime import datetime

from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from database import Base


class ParametroAvaliacao(Base):
    """Critério reutilizável de avaliação, configurado por equipa."""

    __tablename__ = "parametros_avaliacao"

    id = Column(Integer, primary_key=True, index=True)
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="CASCADE"), nullable=False, index=True)
    equipa_id = Column(Integer, ForeignKey("equipas.id", ondelete="CASCADE"), nullable=False, index=True)
    nome = Column(String(120), nullable=False)
    categoria = Column(String(30), nullable=False, index=True)
    descricao = Column(Text, nullable=True)
    valor_minimo = Column(Float, nullable=False, default=0, server_default="0")
    valor_maximo = Column(Float, nullable=False, default=5, server_default="5")
    unidade = Column(String(30), nullable=True)
    ordem = Column(Integer, nullable=False, default=0, server_default="0")
    ativo = Column(Boolean, nullable=False, default=True, server_default="true")
    criado_em = Column(DateTime, nullable=False, default=datetime.now)
    atualizado_em = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    equipa = relationship("Equipa", backref="parametros_avaliacao")
    avaliacoes = relationship(
        "AvaliacaoJogador",
        back_populates="parametro",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class AvaliacaoJogador(Base):
    """Valor atribuído a um jogador num parâmetro, numa data ou sessão."""

    __tablename__ = "avaliacoes_jogadores"

    id = Column(Integer, primary_key=True, index=True)
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="CASCADE"), nullable=False, index=True)
    equipa_id = Column(Integer, ForeignKey("equipas.id", ondelete="CASCADE"), nullable=False, index=True)
    jogador_id = Column(Integer, ForeignKey("jogadores.id", ondelete="CASCADE"), nullable=False, index=True)
    parametro_id = Column(
        Integer,
        ForeignKey("parametros_avaliacao.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sessao_id = Column(
        Integer,
        ForeignKey("sessoes_treino.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    avaliador_id = Column(Integer, ForeignKey("utilizadores.id", ondelete="SET NULL"), nullable=True, index=True)
    data = Column(Date, nullable=False, index=True)
    valor = Column(Float, nullable=False)
    observacao = Column(Text, nullable=True)
    criado_em = Column(DateTime, nullable=False, default=datetime.now)
    atualizado_em = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    jogador = relationship("Jogador", backref="avaliacoes")
    parametro = relationship("ParametroAvaliacao", back_populates="avaliacoes")
    sessao = relationship("SessaoTreino", backref="avaliacoes_jogadores")
    avaliador = relationship("Utilizador", foreign_keys=[avaliador_id])

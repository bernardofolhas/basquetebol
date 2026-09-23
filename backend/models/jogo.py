# ─────────────────────────────────────────────────────────────
# MODELO DE JOGO
# Representa um jogo oficial no calendário da equipa
# ─────────────────────────────────────────────────────────────

from sqlalchemy import Column, Integer, String, Date, Boolean, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import backref, relationship
from database import Base


class Jogo(Base):
    __tablename__ = "jogos"

    id = Column(Integer, primary_key=True, index=True)
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False, index=True)

    # Informações básicas
    data = Column(Date, nullable=False)
    hora = Column(String, nullable=True)           # Ex: "15:00"
    local = Column(String, nullable=True)          # Pavilhão
    adversario = Column(String, nullable=False)    # Nome do adversário
    competicao = Column(String, nullable=True)     # Ex: "Campeonato Nacional"
    numero_jogo = Column(String, nullable=True)

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
    convocados = relationship("Convocado", back_populates="jogo", cascade="all, delete")
    plano = relationship(
        "PlanoJogo",
        back_populates="jogo",
        uselist=False,
        cascade="all, delete-orphan",
        single_parent=True,
    )
    scouting = relationship(
        "RelatorioScouting",
        back_populates="jogo",
        uselist=False,
        cascade="all, delete-orphan",
        single_parent=True,
    )


class Convocado(Base):
    # Jogador convocado para um jogo específico
    __tablename__ = "convocados"
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False, index=True)

    id = Column(Integer, primary_key=True, index=True)

    # Ligação ao jogo e ao jogador
    jogo_id = Column(Integer, ForeignKey("jogos.id", ondelete="CASCADE"), nullable=False)
    jogador_id = Column(Integer, ForeignKey("jogadores.id", ondelete="CASCADE"), nullable=False)

    # Informações da convocatória
    hora_encontro = Column(String, nullable=True)   # Ex: "14:00"
    local_encontro = Column(String, nullable=True)  # Ex: "Pavilhão Municipal"
    observacoes = Column(Text, nullable=True)       # Ex: "Trazer equipamento completo"

    # Relações
    jogo = relationship("Jogo", back_populates="convocados")
    jogador = relationship("Jogador")

class PlanoJogo(Base):
    __tablename__ = "planos_jogo"
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False, index=True)

    id = Column(Integer, primary_key=True, index=True)
    jogo_id = Column(Integer, ForeignKey("jogos.id", ondelete="CASCADE"), nullable=False, unique=True)

    # 5 inicial
    titular_1 = Column(Integer, ForeignKey("jogadores.id", ondelete="SET NULL"), nullable=True)
    titular_2 = Column(Integer, ForeignKey("jogadores.id", ondelete="SET NULL"), nullable=True)
    titular_3 = Column(Integer, ForeignKey("jogadores.id", ondelete="SET NULL"), nullable=True)
    titular_4 = Column(Integer, ForeignKey("jogadores.id", ondelete="SET NULL"), nullable=True)
    titular_5 = Column(Integer, ForeignKey("jogadores.id", ondelete="SET NULL"), nullable=True)
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

    jogo = relationship("Jogo", back_populates="plano")
    grupos_rotacao = relationship(
        "PlanoJogoRotacao",
        back_populates="plano",
        cascade="all, delete-orphan",
        order_by="PlanoJogoRotacao.grupo, PlanoJogoRotacao.ordem",
    )
    itens = relationship(
        "PlanoJogoItem",
        back_populates="plano",
        cascade="all, delete-orphan",
        order_by="PlanoJogoItem.ordem, PlanoJogoItem.id",
    )
    jogadas = relationship(
        "PlanoJogoJogada",
        back_populates="plano",
        cascade="all, delete-orphan",
        order_by="PlanoJogoJogada.ordem, PlanoJogoJogada.id",
    )


class PlanoJogoRotacao(Base):
    __tablename__ = "plano_jogo_rotacoes"
    __table_args__ = (
        UniqueConstraint("plano_jogo_id", "grupo", "ordem", name="uq_plano_rotacao_posicao"),
    )

    id = Column(Integer, primary_key=True, index=True)
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False, index=True)
    plano_jogo_id = Column(Integer, ForeignKey("planos_jogo.id", ondelete="CASCADE"), nullable=False, index=True)
    grupo = Column(Integer, nullable=False)
    ordem = Column(Integer, nullable=False)
    jogador_id = Column(Integer, ForeignKey("jogadores.id", ondelete="CASCADE"), nullable=False, index=True)

    plano = relationship("PlanoJogo", back_populates="grupos_rotacao")
    jogador = relationship("Jogador")


class ItemPlanoJogoBiblioteca(Base):
    __tablename__ = "plano_jogo_biblioteca"
    __table_args__ = (
        UniqueConstraint("equipa_id", "categoria", "texto_normalizado", name="uq_plano_biblioteca_item"),
    )

    id = Column(Integer, primary_key=True, index=True)
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False, index=True)
    equipa_id = Column(Integer, ForeignKey("equipas.id", ondelete="CASCADE"), nullable=False, index=True)
    categoria = Column(String(48), nullable=False, index=True)
    texto = Column(Text, nullable=False)
    texto_normalizado = Column(String(240), nullable=False)
    ativo = Column(Boolean, nullable=False, default=True)

    equipa = relationship("Equipa")
    utilizacoes = relationship("PlanoJogoItem", back_populates="item")


class PlanoJogoItem(Base):
    __tablename__ = "plano_jogo_itens"
    __table_args__ = (
        UniqueConstraint("plano_jogo_id", "item_id", name="uq_plano_jogo_item"),
    )

    id = Column(Integer, primary_key=True, index=True)
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False, index=True)
    plano_jogo_id = Column(Integer, ForeignKey("planos_jogo.id", ondelete="CASCADE"), nullable=False, index=True)
    item_id = Column(Integer, ForeignKey("plano_jogo_biblioteca.id", ondelete="CASCADE"), nullable=False, index=True)
    ordem = Column(Integer, nullable=False, default=0)

    plano = relationship("PlanoJogo", back_populates="itens")
    item = relationship("ItemPlanoJogoBiblioteca", back_populates="utilizacoes")


class PlanoJogoJogada(Base):
    __tablename__ = "plano_jogo_jogadas"
    __table_args__ = (
        UniqueConstraint("plano_jogo_id", "setplay_id", name="uq_plano_jogo_setplay"),
    )

    id = Column(Integer, primary_key=True, index=True)
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False, index=True)
    plano_jogo_id = Column(Integer, ForeignKey("planos_jogo.id", ondelete="CASCADE"), nullable=False, index=True)
    setplay_id = Column(Integer, ForeignKey("setplays.id", ondelete="CASCADE"), nullable=False, index=True)
    ordem = Column(Integer, nullable=False, default=0)

    plano = relationship("PlanoJogo", back_populates="jogadas")
    setplay = relationship("SetPlay")

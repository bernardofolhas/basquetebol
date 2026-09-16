"""Registos de scouting de adversários e auto-scouting, sempre ligados a um jogo."""

from datetime import datetime

from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
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


# Departamento de Scouting. Estes registos são permanentes por adversário e
# independentes dos relatórios históricos criados para cada jogo.
class ScoutingAdversario(Base):
    __tablename__ = "scouting_adversarios"
    __table_args__ = (UniqueConstraint("clube_id", "nome_normalizado", name="uq_scouting_adversario_clube_nome"),)

    id = Column(Integer, primary_key=True, index=True)
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="CASCADE"), nullable=False, index=True)
    nome = Column(String(160), nullable=False)
    nome_normalizado = Column(String(160), nullable=False)
    observacoes = Column(Text, nullable=True)
    criado_em = Column(DateTime, nullable=False, default=datetime.now)
    atualizado_em = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    jogos = relationship("ScoutingAdversarioJogo", back_populates="adversario", cascade="all, delete-orphan")
    jogadores = relationship("ScoutingJogador", back_populates="adversario", cascade="all, delete-orphan", order_by="ScoutingJogador.numero, ScoutingJogador.nome")


class ScoutingAdversarioJogo(Base):
    __tablename__ = "scouting_adversarios_jogos"
    __table_args__ = (UniqueConstraint("jogo_id", name="uq_scouting_adversario_jogo"),)

    id = Column(Integer, primary_key=True)
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="CASCADE"), nullable=False, index=True)
    adversario_id = Column(Integer, ForeignKey("scouting_adversarios.id", ondelete="CASCADE"), nullable=False, index=True)
    jogo_id = Column(Integer, ForeignKey("jogos.id", ondelete="CASCADE"), nullable=False, index=True)
    criado_em = Column(DateTime, nullable=False, default=datetime.now)

    adversario = relationship("ScoutingAdversario", back_populates="jogos")
    jogo = relationship("Jogo")


class ScoutingJogador(Base):
    __tablename__ = "scouting_roster_jogadores"

    id = Column(Integer, primary_key=True, index=True)
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="CASCADE"), nullable=False, index=True)
    adversario_id = Column(Integer, ForeignKey("scouting_adversarios.id", ondelete="CASCADE"), nullable=False, index=True)
    fotografia = Column(String(300), nullable=True)
    nome = Column(String(160), nullable=False)
    numero = Column(String(12), nullable=True)
    idade = Column(Integer, nullable=True)
    posicao_principal = Column(String(24), nullable=False)
    posicao_alternativa = Column(String(24), nullable=True)
    altura_cm = Column(Float, nullable=True)
    peso_kg = Column(Float, nullable=True)
    equipa_anterior = Column(String(160), nullable=True)
    estado = Column(String(24), nullable=False, default="ativo")
    mao_dominante = Column(String(24), nullable=True)
    observacoes = Column(Text, nullable=True)
    criado_em = Column(DateTime, nullable=False, default=datetime.now)
    atualizado_em = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    adversario = relationship("ScoutingAdversario", back_populates="jogadores")
    ficha = relationship("ScoutingFichaIndividual", back_populates="jogador", uselist=False, cascade="all, delete-orphan")
    media_epoca = relationship("ScoutingMediaEpoca", back_populates="jogador", uselist=False, cascade="all, delete-orphan")
    estatisticas = relationship("ScoutingEstatisticaJogo", back_populates="jogador", cascade="all, delete-orphan", order_by="ScoutingEstatisticaJogo.data.desc()")
    itens = relationship("ScoutingJogadorItem", back_populates="jogador", cascade="all, delete-orphan")
    zonas = relationship("ScoutingZonaAcao", back_populates="jogador", cascade="all, delete-orphan")


class ScoutingFichaIndividual(Base):
    __tablename__ = "scouting_fichas_individuais"

    id = Column(Integer, primary_key=True)
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="CASCADE"), nullable=False, index=True)
    jogador_id = Column(Integer, ForeignKey("scouting_roster_jogadores.id", ondelete="CASCADE"), nullable=False, unique=True)
    resumo = Column(Text, nullable=True)
    atualizado_em = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)
    jogador = relationship("ScoutingJogador", back_populates="ficha")


STAT_FIELDS = ("minutos", "pontos", "fg_c", "fg_t", "dois_c", "dois_t", "tres_c", "tres_t", "ll_c", "ll_t", "ress_of", "ress_def", "ress_total", "assistencias", "faltas", "turnovers", "roubos", "desarmes", "mais_menos", "eficiencia")


class _ScoutingStatMixin:
    minutos = Column(Float, nullable=True)
    pontos = Column(Float, nullable=True)
    fg_c = Column(Float, nullable=True)
    fg_t = Column(Float, nullable=True)
    dois_c = Column(Float, nullable=True)
    dois_t = Column(Float, nullable=True)
    tres_c = Column(Float, nullable=True)
    tres_t = Column(Float, nullable=True)
    ll_c = Column(Float, nullable=True)
    ll_t = Column(Float, nullable=True)
    ress_of = Column(Float, nullable=True)
    ress_def = Column(Float, nullable=True)
    ress_total = Column(Float, nullable=True)
    assistencias = Column(Float, nullable=True)
    faltas = Column(Float, nullable=True)
    turnovers = Column(Float, nullable=True)
    roubos = Column(Float, nullable=True)
    desarmes = Column(Float, nullable=True)
    mais_menos = Column(Float, nullable=True)
    eficiencia = Column(Float, nullable=True)


class ScoutingMediaEpoca(_ScoutingStatMixin, Base):
    __tablename__ = "scouting_medias_epoca"
    id = Column(Integer, primary_key=True)
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="CASCADE"), nullable=False, index=True)
    jogador_id = Column(Integer, ForeignKey("scouting_roster_jogadores.id", ondelete="CASCADE"), nullable=False, unique=True)
    jogador = relationship("ScoutingJogador", back_populates="media_epoca")


class ScoutingEstatisticaJogo(_ScoutingStatMixin, Base):
    __tablename__ = "scouting_estatisticas_jogo"
    __table_args__ = (UniqueConstraint("jogador_id", "jogo_id", name="uq_scouting_estatistica_jogador_jogo"),)
    id = Column(Integer, primary_key=True)
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="CASCADE"), nullable=False, index=True)
    jogador_id = Column(Integer, ForeignKey("scouting_roster_jogadores.id", ondelete="CASCADE"), nullable=False, index=True)
    jogo_id = Column(Integer, ForeignKey("jogos.id", ondelete="SET NULL"), nullable=True, index=True)
    data = Column(Date, nullable=False)
    adversario = Column(String(160), nullable=True)
    competicao = Column(String(160), nullable=True)
    jogador = relationship("ScoutingJogador", back_populates="estatisticas")
    jogo = relationship("Jogo")


class ScoutingItemBiblioteca(Base):
    __tablename__ = "scouting_biblioteca_itens"
    __table_args__ = (UniqueConstraint("clube_id", "categoria", "nome_normalizado", name="uq_scouting_biblioteca_item"),)
    id = Column(Integer, primary_key=True)
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="CASCADE"), nullable=False, index=True)
    categoria = Column(String(32), nullable=False, index=True)
    nome = Column(String(160), nullable=False)
    nome_normalizado = Column(String(160), nullable=False)
    jogadores = relationship("ScoutingJogadorItem", back_populates="item", cascade="all, delete-orphan")


class ScoutingJogadorItem(Base):
    __tablename__ = "scouting_jogadores_itens"
    __table_args__ = (UniqueConstraint("jogador_id", "item_id", name="uq_scouting_jogador_item"),)
    id = Column(Integer, primary_key=True)
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="CASCADE"), nullable=False, index=True)
    jogador_id = Column(Integer, ForeignKey("scouting_roster_jogadores.id", ondelete="CASCADE"), nullable=False, index=True)
    item_id = Column(Integer, ForeignKey("scouting_biblioteca_itens.id", ondelete="CASCADE"), nullable=False, index=True)
    observacao = Column(Text, nullable=True)
    jogador = relationship("ScoutingJogador", back_populates="itens")
    item = relationship("ScoutingItemBiblioteca", back_populates="jogadores")


class ScoutingZonaAcao(Base):
    __tablename__ = "scouting_zonas_acao"
    __table_args__ = (UniqueConstraint("jogador_id", "zona", name="uq_scouting_jogador_zona"),)
    id = Column(Integer, primary_key=True)
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="CASCADE"), nullable=False, index=True)
    jogador_id = Column(Integer, ForeignKey("scouting_roster_jogadores.id", ondelete="CASCADE"), nullable=False, index=True)
    zona = Column(String(48), nullable=False)
    observacao = Column(Text, nullable=True)
    jogador = relationship("ScoutingJogador", back_populates="zonas")

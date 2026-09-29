"""Registos de scouting de adversários e auto-scouting, sempre ligados a um jogo."""

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, Column, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
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
    simbolo = Column(String(255), nullable=True)
    observacoes = Column(Text, nullable=True)
    criado_em = Column(DateTime, nullable=False, default=datetime.now)
    atualizado_em = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    jogos = relationship("ScoutingAdversarioJogo", back_populates="adversario", cascade="all, delete-orphan")
    jogadores = relationship("ScoutingJogador", back_populates="adversario", cascade="all, delete-orphan", order_by="ScoutingJogador.numero, ScoutingJogador.nome")
    resultados = relationship("ScoutingResultadoColetivo", back_populates="adversario_scouting", cascade="all, delete-orphan", order_by="ScoutingResultadoColetivo.data.desc()")
    estatisticas_coletivas = relationship("ScoutingEstatisticaColetivaJogo", back_populates="adversario_scouting", cascade="all, delete-orphan", order_by="ScoutingEstatisticaColetivaJogo.data.desc()")
    media_coletiva = relationship("ScoutingMediaColetiva", back_populates="adversario_scouting", uselist=False, cascade="all, delete-orphan")
    itens_coletivos = relationship("ScoutingAdversarioItem", back_populates="adversario_scouting", cascade="all, delete-orphan")
    lideres = relationship("ScoutingLiderEstatistico", back_populates="adversario_scouting", cascade="all, delete-orphan")
    opcoes_defensivas = relationship("ScoutingOpcoesDefensivas", back_populates="adversario_scouting", uselist=False, cascade="all, delete-orphan")
    conceitos_ofensivos = relationship("ScoutingConceitoOfensivo", back_populates="adversario_scouting", cascade="all, delete-orphan", order_by="ScoutingConceitoOfensivo.ordem")
    momentos_playbook = relationship("ScoutingMomentoPlaybook", back_populates="adversario_scouting", cascade="all, delete-orphan", order_by="ScoutingMomentoPlaybook.ordem")
    rotacao_prevista = relationship("ScoutingRotacaoPrevista", back_populates="adversario_scouting", cascade="all, delete-orphan", order_by="ScoutingRotacaoPrevista.papel, ScoutingRotacaoPrevista.ordem")


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
    rotacoes_previstas = relationship("ScoutingRotacaoPrevista", back_populates="jogador", cascade="all, delete-orphan")


class ScoutingGrupoAvaliacao(Base):
    __tablename__ = "scouting_grupos_avaliacao"
    __table_args__ = (
        UniqueConstraint("clube_id", "nome_normalizado", name="uq_scouting_grupo_avaliacao_clube_nome"),
    )

    id = Column(Integer, primary_key=True, index=True)
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="CASCADE"), nullable=False, index=True)
    nome = Column(String(120), nullable=False)
    nome_normalizado = Column(String(120), nullable=False)
    ordem = Column(Integer, nullable=False, default=0)
    ativo = Column(Boolean, nullable=False, default=True)
    criado_em = Column(DateTime, nullable=False, default=datetime.now)
    atualizado_em = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    itens = relationship("ScoutingItemBiblioteca", back_populates="grupo")


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
    grupo_id = Column(Integer, ForeignKey("scouting_grupos_avaliacao.id", ondelete="SET NULL"), nullable=True, index=True)
    categoria = Column(String(32), nullable=False, index=True)
    nome = Column(String(160), nullable=False)
    nome_normalizado = Column(String(160), nullable=False)
    ordem = Column(Integer, nullable=False, default=0)
    ativo = Column(Boolean, nullable=False, default=True)
    grupo = relationship("ScoutingGrupoAvaliacao", back_populates="itens")
    jogadores = relationship("ScoutingJogadorItem", back_populates="item", cascade="all, delete-orphan")


class ScoutingJogadorItem(Base):
    __tablename__ = "scouting_jogadores_itens"
    __table_args__ = (
        UniqueConstraint("jogador_id", "item_id", name="uq_scouting_jogador_item"),
        CheckConstraint("avaliacao IS NULL OR (avaliacao >= 1 AND avaliacao <= 5)", name="ck_scouting_jogador_item_avaliacao"),
        CheckConstraint("prioridade IS NULL OR (prioridade >= 1 AND prioridade <= 3)", name="ck_scouting_jogador_item_prioridade"),
    )
    id = Column(Integer, primary_key=True)
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="CASCADE"), nullable=False, index=True)
    jogador_id = Column(Integer, ForeignKey("scouting_roster_jogadores.id", ondelete="CASCADE"), nullable=False, index=True)
    item_id = Column(Integer, ForeignKey("scouting_biblioteca_itens.id", ondelete="CASCADE"), nullable=False, index=True)
    observacao = Column(Text, nullable=True)
    avaliacao = Column(Integer, nullable=True)
    prioridade = Column(Integer, nullable=True)
    ordem = Column(Integer, nullable=False, default=0)
    destaque = Column(Boolean, nullable=False, default=False)
    ordem_destaque = Column(Integer, nullable=True)
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


class ScoutingResultadoColetivo(Base):
    __tablename__ = "scouting_resultados_coletivos"
    __table_args__ = (UniqueConstraint("adversario_id", "jogo_id", name="uq_scouting_resultado_jogo"),)
    id = Column(Integer, primary_key=True)
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="CASCADE"), nullable=False, index=True)
    adversario_id = Column(Integer, ForeignKey("scouting_adversarios.id", ondelete="CASCADE"), nullable=False, index=True)
    jogo_id = Column(Integer, ForeignKey("jogos.id", ondelete="SET NULL"), nullable=True, index=True)
    data = Column(Date, nullable=False)
    oponente = Column(String(160), nullable=False)
    em_casa = Column(Boolean, nullable=False, default=True)
    pontos_marcados = Column(Integer, nullable=True)
    pontos_sofridos = Column(Integer, nullable=True)
    competicao = Column(String(160), nullable=True)
    adversario_scouting = relationship("ScoutingAdversario", back_populates="resultados")
    jogo = relationship("Jogo")


class ScoutingMediaColetiva(_ScoutingStatMixin, Base):
    __tablename__ = "scouting_medias_coletivas"
    id = Column(Integer, primary_key=True)
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="CASCADE"), nullable=False, index=True)
    adversario_id = Column(Integer, ForeignKey("scouting_adversarios.id", ondelete="CASCADE"), nullable=False, unique=True)
    usar_manual = Column(Boolean, nullable=False, default=False)
    adversario_scouting = relationship("ScoutingAdversario", back_populates="media_coletiva")


class ScoutingEstatisticaColetivaJogo(_ScoutingStatMixin, Base):
    __tablename__ = "scouting_estatisticas_coletivas_jogo"
    __table_args__ = (UniqueConstraint("adversario_id", "resultado_id", name="uq_scouting_estatistica_coletiva_resultado"),)
    id = Column(Integer, primary_key=True)
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="CASCADE"), nullable=False, index=True)
    adversario_id = Column(Integer, ForeignKey("scouting_adversarios.id", ondelete="CASCADE"), nullable=False, index=True)
    resultado_id = Column(Integer, ForeignKey("scouting_resultados_coletivos.id", ondelete="CASCADE"), nullable=True, index=True)
    data = Column(Date, nullable=False)
    adversario_scouting = relationship("ScoutingAdversario", back_populates="estatisticas_coletivas")
    resultado = relationship("ScoutingResultadoColetivo")


class ScoutingAdversarioItem(Base):
    __tablename__ = "scouting_adversarios_itens"
    __table_args__ = (UniqueConstraint("adversario_id", "item_id", name="uq_scouting_adversario_item"),)
    id = Column(Integer, primary_key=True)
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="CASCADE"), nullable=False, index=True)
    adversario_id = Column(Integer, ForeignKey("scouting_adversarios.id", ondelete="CASCADE"), nullable=False, index=True)
    item_id = Column(Integer, ForeignKey("scouting_biblioteca_itens.id", ondelete="CASCADE"), nullable=False, index=True)
    observacao = Column(Text, nullable=True)
    valor = Column(String(80), nullable=True)
    ranking = Column(String(80), nullable=True)
    validade = Column(String(120), nullable=True)
    adversario_scouting = relationship("ScoutingAdversario", back_populates="itens_coletivos")
    item = relationship("ScoutingItemBiblioteca")


class ScoutingLiderEstatistico(Base):
    __tablename__ = "scouting_lideres_estatisticos"
    id = Column(Integer, primary_key=True)
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="CASCADE"), nullable=False, index=True)
    adversario_id = Column(Integer, ForeignKey("scouting_adversarios.id", ondelete="CASCADE"), nullable=False, index=True)
    jogador_id = Column(Integer, ForeignKey("scouting_roster_jogadores.id", ondelete="CASCADE"), nullable=False, index=True)
    tipo = Column(String(120), nullable=False)
    observacao = Column(Text, nullable=True)
    adversario_scouting = relationship("ScoutingAdversario", back_populates="lideres")
    jogador = relationship("ScoutingJogador")


class ScoutingOpcoesDefensivas(Base):
    __tablename__ = "scouting_opcoes_defensivas"
    id = Column(Integer, primary_key=True)
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="CASCADE"), nullable=False, index=True)
    adversario_id = Column(Integer, ForeignKey("scouting_adversarios.id", ondelete="CASCADE"), nullable=False, unique=True)
    bloqueio_central = Column(Boolean, nullable=False, default=False)
    bloqueio_central_notas = Column(Text, nullable=True)
    bloqueio_lateral = Column(Boolean, nullable=False, default=False)
    bloqueio_lateral_notas = Column(Text, nullable=True)
    bloqueio_indireto = Column(Boolean, nullable=False, default=False)
    bloqueio_indireto_notas = Column(Text, nullable=True)
    handoff = Column(Boolean, nullable=False, default=False)
    handoff_notas = Column(Text, nullable=True)
    bola_interior = Column(Boolean, nullable=False, default=False)
    bola_interior_notas = Column(Text, nullable=True)
    alteracoes = Column(Boolean, nullable=False, default=False)
    alteracoes_notas = Column(Text, nullable=True)
    adversario_scouting = relationship("ScoutingAdversario", back_populates="opcoes_defensivas")


class ScoutingConceitoOfensivo(Base):
    __tablename__ = "scouting_conceitos_ofensivos"
    id = Column(Integer, primary_key=True)
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="CASCADE"), nullable=False, index=True)
    adversario_id = Column(Integer, ForeignKey("scouting_adversarios.id", ondelete="CASCADE"), nullable=False, index=True)
    setplay_id = Column(Integer, ForeignKey("setplays.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    ordem = Column(Integer, nullable=False, default=0)
    adversario_scouting = relationship("ScoutingAdversario", back_populates="conceitos_ofensivos")
    setplay = relationship("SetPlay")


class ScoutingMomentoPlaybook(Base):
    __tablename__ = "scouting_momentos_playbook"
    id = Column(Integer, primary_key=True)
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="CASCADE"), nullable=False, index=True)
    adversario_id = Column(Integer, ForeignKey("scouting_adversarios.id", ondelete="CASCADE"), nullable=False, index=True)
    setplay_id = Column(Integer, ForeignKey("setplays.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    ordem = Column(Integer, nullable=False, default=0)
    adversario_scouting = relationship("ScoutingAdversario", back_populates="momentos_playbook")
    setplay = relationship("SetPlay")


class ScoutingRotacaoPrevista(Base):
    __tablename__ = "scouting_rotacoes_previstas"
    __table_args__ = (UniqueConstraint("adversario_id", "jogador_id", name="uq_scouting_rotacao_adversario_jogador"),)
    id = Column(Integer, primary_key=True)
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="CASCADE"), nullable=False, index=True)
    adversario_id = Column(Integer, ForeignKey("scouting_adversarios.id", ondelete="CASCADE"), nullable=False, index=True)
    jogador_id = Column(Integer, ForeignKey("scouting_roster_jogadores.id", ondelete="CASCADE"), nullable=False, index=True)
    papel = Column(String(16), nullable=False)
    ordem = Column(Integer, nullable=False, default=0)
    adversario_scouting = relationship("ScoutingAdversario", back_populates="rotacao_prevista")
    jogador = relationship("ScoutingJogador", back_populates="rotacoes_previstas")

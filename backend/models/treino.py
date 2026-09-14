# ─────────────────────────────────────────────────────────────
# MODELO DE PLANO DE TREINO
# Baseado no formato do documento Word de referência:
# Cabeçalho + Blocos (A, B, C, D) + Exercícios por bloco
# Cada exercício tem: hora, minutos, campos de desenho,
# organização e coaching points
# ─────────────────────────────────────────────────────────────

from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.orm import relationship
from database import Base


class PlanoTreino(Base):
    # Plano de treino associado a uma sessão específica
    __tablename__ = "planos_treino"
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False, index=True)

    id = Column(Integer, primary_key=True, index=True)

    # Ligação à sessão — unique=True garante um plano por sessão
    sessao_id = Column(
        Integer,
        ForeignKey("sessoes_treino.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    # Cabeçalho do plano (alguns campos vêm da sessão automaticamente)
    hora_inicio = Column(String, nullable=True)  # Ex: "18:00"
    escalao = Column(String, nullable=True)       # Ex: "U18"

    # Objectivos gerais do treino
    objectivos = Column(Text, nullable=True)

    # Reflexão após o treino
    reflexao = Column(Text, nullable=True)

    # Organização operacional da sessão, mantida separada do conteúdo técnico.
    atletas_previstos = Column(Text, nullable=True)
    equipas_aleatorias = Column(Text, nullable=True)

    # relationship — uselist=False indica relação um-para-um
    sessao = relationship("SessaoTreino", back_populates="plano_treino", uselist=False)

    # Um plano tem vários exercícios organizados por blocos e ordem
    # cascade="all, delete" — apagar o plano apaga os exercícios
    exercicios = relationship("ExercicioPlano", back_populates="plano",
                              cascade="all, delete",
                              order_by="ExercicioPlano.bloco, ExercicioPlano.ordem")
    blocos = relationship("BlocoTreino", back_populates="plano", cascade="all, delete-orphan", order_by="BlocoTreino.ordem")
    importacoes = relationship(
        "ImportacaoPlanoTreino",
        back_populates="plano",
        cascade="all, delete-orphan",
        order_by="ImportacaoPlanoTreino.criado_em.desc()",
    )


class ImportacaoPlanoTreino(Base):
    """Ficheiro original e rascunho reconhecido antes de entrar no plano."""

    __tablename__ = "importacoes_plano_treino"

    id = Column(Integer, primary_key=True, index=True)
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False, index=True)
    plano_id = Column(Integer, ForeignKey("planos_treino.id", ondelete="CASCADE"), nullable=False, index=True)
    utilizador_id = Column(Integer, ForeignKey("utilizadores.id", ondelete="SET NULL"), nullable=True, index=True)
    nome_original = Column(String(255), nullable=False)
    tipo_mime = Column(String(120), nullable=False)
    tamanho_bytes = Column(Integer, nullable=False)
    ficheiro = Column(LargeBinary, nullable=False)
    texto_extraido = Column(Text, nullable=True)
    dados_json = Column(Text, nullable=False, default="{}", server_default="{}")
    estado = Column(String(30), nullable=False, default="em_revisao", server_default="em_revisao")
    confianca = Column(Float, nullable=True)
    aviso = Column(Text, nullable=True)
    criado_em = Column(DateTime, nullable=False, default=datetime.now)
    atualizado_em = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    plano = relationship("PlanoTreino", back_populates="importacoes")


class BlocoTreino(Base):
    __tablename__ = "blocos_treino"
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False, index=True)

    id = Column(Integer, primary_key=True, index=True)
    plano_id = Column(Integer, ForeignKey("planos_treino.id", ondelete="CASCADE"), nullable=False)
    nome = Column(String, nullable=False)
    tipo = Column(String, nullable=True)
    ordem = Column(Integer, nullable=False, default=1)

    plano = relationship("PlanoTreino", back_populates="blocos")
    exercicios = relationship("ExercicioPlano", back_populates="bloco_dinamico", order_by="ExercicioPlano.ordem")


class ExercicioPlano(Base):
    # Cada exercício dentro de um plano de treino
    # Corresponde a uma linha da tabela do documento Word
    __tablename__ = "exercicios_plano"
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False, index=True)

    id = Column(Integer, primary_key=True, index=True)

    # Ligação ao plano de treino
    plano_id = Column(Integer, ForeignKey("planos_treino.id"), nullable=False)

    # Bloco do treino (A, B, C ou D — como no documento)
    bloco = Column(String, nullable=True)
    bloco_id = Column(Integer, ForeignKey("blocos_treino.id", ondelete="SET NULL"), nullable=True)

    # Ordem dentro do bloco (1, 2, 3...)
    ordem = Column(Integer, nullable=False, default=1)

    # Hora e duração do exercício
    hora = Column(String, nullable=True)       # Ex: "18:15"
    minutos = Column(Integer, nullable=True)   # Duração em minutos
    rpe = Column(Float, nullable=True)          # RPE do exercício (escala 1-10)

    # Nome/título do exercício
    nome = Column(String, nullable=True)

    # Categoria do exercício (TIO, TID, TCO, etc.)
    categoria = Column(String, nullable=True)

    # Cada desenho guarda a imagem de apresentação e, nas versões novas,
    # o estado vetorial que permite voltar a selecionar os seus elementos.
    desenho_1 = Column(Text, nullable=True)  # Campo meio court
    desenho_2 = Column(Text, nullable=True)  # Campo completo
    # Campos de desenho extra (opcionais)
    desenho_3 = Column(Text, nullable=True)  # Campo meio extra
    desenho_4 = Column(Text, nullable=True)  # Campo completo extra
    # Os primeiros quatro campos mantêm as colunas legadas. Os seguintes ficam
    # neste mapa extensível, sem impor um limite ao número de quadros.
    desenhos_campos = Column(Text, nullable=False, default="{}", server_default="{}")
    # Lista ordenada das posições visíveis. Permite um exercício sem campos.
    campos_ativos = Column(String, nullable=False, default="1,2", server_default="1,2")

    # Organização do exercício
    organizacao = Column(Text, nullable=True)

    # Coaching Points — pontos importantes a transmitir aos jogadores
    coaching_points = Column(Text, nullable=True)

    # Relação com o plano
    plano = relationship("PlanoTreino", back_populates="exercicios")
    bloco_dinamico = relationship("BlocoTreino", back_populates="exercicios")


class BibliotecoExercicio(Base):
    __tablename__ = "biblioteca_exercicios"

    id = Column(Integer, primary_key=True, index=True)
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False, index=True)
    nome = Column(String, nullable=False, index=True)
    categoria = Column(String, nullable=True)
    descricao = Column(Text, nullable=True)
    organizacao = Column(Text, nullable=True)
    coaching_points = Column(Text, nullable=True)
    desenho = Column(Text, nullable=True)      # base64 PNG, half-court
    desenho_campo_completo = Column(Text, nullable=True)
    tags = Column(String, nullable=True)

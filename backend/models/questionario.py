from datetime import date, datetime

import json

from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from database import Base


class RespostaQuestionarioDiario(Base):
    __tablename__ = "respostas_questionario_diario"

    id = Column(Integer, primary_key=True, index=True)
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False, index=True)
    jogador_id = Column(Integer, ForeignKey("jogadores.id", ondelete="CASCADE"), nullable=False, index=True)
    data = Column(Date, nullable=False, default=date.today, index=True)
    tipo_sessao = Column(String, nullable=False)
    horas_sono = Column(Float, nullable=True)
    qualidade_sono = Column(Integer, nullable=False)
    pse_esforco = Column(Integer, nullable=False)
    dor_membros_inferiores = Column(Integer, nullable=False)
    dor_membros_superiores = Column(Integer, nullable=False)
    tem_queixa = Column(Boolean, nullable=False, default=False)
    descricao_queixa = Column(Text, nullable=True)
    observacoes = Column(Text, nullable=True)
    criado_em = Column(DateTime, nullable=False, default=datetime.now)
    atualizado_em = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    jogador = relationship("Jogador", backref="respostas_questionario_diario")


class QuestionarioPersonalizado(Base):
    __tablename__ = "questionarios_personalizados"

    id = Column(Integer, primary_key=True, index=True)
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False, index=True)
    equipa_id = Column(Integer, ForeignKey("equipas.id", ondelete="CASCADE"), nullable=False, index=True)
    nome = Column(String(180), nullable=False)
    descricao = Column(Text, nullable=True)
    origem_modelo = Column(String(80), nullable=True)
    regra_aplicacao = Column(String(30), nullable=False, default="manual", server_default="manual")
    ativo = Column(Boolean, nullable=False, default=True)
    criado_em = Column(DateTime, nullable=False, default=datetime.now)
    atualizado_em = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    equipa = relationship("Equipa", backref="questionarios_personalizados")
    perguntas = relationship(
        "PerguntaQuestionario",
        back_populates="questionario",
        cascade="all, delete-orphan",
        order_by="PerguntaQuestionario.ordem, PerguntaQuestionario.id",
    )
    aplicacoes = relationship(
        "AplicacaoQuestionario",
        back_populates="questionario",
        cascade="all, delete-orphan",
        order_by="AplicacaoQuestionario.data.desc(), AplicacaoQuestionario.id.desc()",
    )


class PerguntaQuestionario(Base):
    __tablename__ = "perguntas_questionario"

    id = Column(Integer, primary_key=True, index=True)
    questionario_id = Column(
        Integer,
        ForeignKey("questionarios_personalizados.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    texto = Column(String(300), nullable=False)
    ajuda = Column(String(300), nullable=True)
    tipo = Column(String(30), nullable=False)
    obrigatoria = Column(Boolean, nullable=False, default=True)
    ordem = Column(Integer, nullable=False, default=0)
    minimo = Column(Float, nullable=True)
    maximo = Column(Float, nullable=True)
    rotulo_minimo = Column(String(80), nullable=True)
    rotulo_maximo = Column(String(80), nullable=True)
    opcoes_json = Column(Text, nullable=True)

    questionario = relationship("QuestionarioPersonalizado", back_populates="perguntas")

    @property
    def opcoes(self) -> list[str]:
        try:
            valores = json.loads(self.opcoes_json or "[]")
            return [str(valor) for valor in valores] if isinstance(valores, list) else []
        except (TypeError, ValueError):
            return []


class AplicacaoQuestionario(Base):
    __tablename__ = "aplicacoes_questionario"

    id = Column(Integer, primary_key=True, index=True)
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False, index=True)
    equipa_id = Column(Integer, ForeignKey("equipas.id", ondelete="CASCADE"), nullable=False, index=True)
    questionario_id = Column(
        Integer,
        ForeignKey("questionarios_personalizados.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sessao_treino_id = Column(
        Integer,
        ForeignKey("sessoes_treino.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    data = Column(Date, nullable=False, index=True)
    titulo = Column(String(180), nullable=True)
    permite_multiplas = Column(Boolean, nullable=False, default=False)
    automatica = Column(Boolean, nullable=False, default=False, server_default="false")
    ativa = Column(Boolean, nullable=False, default=True)
    criado_em = Column(DateTime, nullable=False, default=datetime.now)

    questionario = relationship("QuestionarioPersonalizado", back_populates="aplicacoes")
    equipa = relationship("Equipa")
    sessao_treino = relationship("SessaoTreino")
    submissoes = relationship(
        "SubmissaoQuestionario",
        back_populates="aplicacao",
        cascade="all, delete-orphan",
        order_by="SubmissaoQuestionario.criado_em.desc()",
    )


class SubmissaoQuestionario(Base):
    __tablename__ = "submissoes_questionario"

    id = Column(Integer, primary_key=True, index=True)
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False, index=True)
    aplicacao_id = Column(
        Integer,
        ForeignKey("aplicacoes_questionario.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    jogador_id = Column(Integer, ForeignKey("jogadores.id", ondelete="CASCADE"), nullable=False, index=True)
    criado_em = Column(DateTime, nullable=False, default=datetime.now)
    atualizado_em = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    aplicacao = relationship("AplicacaoQuestionario", back_populates="submissoes")
    jogador = relationship("Jogador")
    respostas = relationship(
        "RespostaPerguntaQuestionario",
        back_populates="submissao",
        cascade="all, delete-orphan",
    )


class RespostaPerguntaQuestionario(Base):
    __tablename__ = "respostas_perguntas_questionario"
    __table_args__ = (
        UniqueConstraint("submissao_id", "pergunta_id", name="uq_resposta_submissao_pergunta"),
    )

    id = Column(Integer, primary_key=True, index=True)
    submissao_id = Column(
        Integer,
        ForeignKey("submissoes_questionario.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    pergunta_id = Column(
        Integer,
        ForeignKey("perguntas_questionario.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    valor = Column(Text, nullable=True)

    submissao = relationship("SubmissaoQuestionario", back_populates="respostas")
    pergunta = relationship("PerguntaQuestionario")

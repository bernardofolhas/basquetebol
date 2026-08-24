import enum
from datetime import datetime

from sqlalchemy import Boolean, Column, Date, DateTime, Enum, ForeignKey, Integer, String, Table, Text
from sqlalchemy.orm import relationship

from database import Base


evento_planeamento_clube_equipa = Table(
    "evento_planeamento_clube_equipa",
    Base.metadata,
    Column("evento_id", Integer, ForeignKey("eventos_planeamento_clube.id"), primary_key=True),
    Column("equipa_id", Integer, ForeignKey("equipas.id"), primary_key=True),
)


class PlaneamentoClubeAnual(Base):
    __tablename__ = "planeamentos_clube_anuais"

    id = Column(Integer, primary_key=True, index=True)
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False, index=True)
    epoca = Column(String, nullable=False)
    titulo = Column(String, nullable=False)
    data_inicio = Column(Date, nullable=False)
    data_fim = Column(Date, nullable=False)
    objetivos_gerais = Column(Text, nullable=True)
    observacoes = Column(Text, nullable=True)
    ativo = Column(Boolean, default=True, nullable=False)
    criado_em = Column(DateTime, default=datetime.now, nullable=False)
    atualizado_em = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)

    planeamentos_mensais = relationship(
        "PlaneamentoClubeMensal",
        back_populates="planeamento_anual",
        cascade="all, delete",
    )
    eventos = relationship(
        "EventoPlaneamentoClube",
        back_populates="planeamento_anual",
        cascade="all, delete",
    )


class PlaneamentoClubeMensal(Base):
    __tablename__ = "planeamentos_clube_mensais"
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False, index=True)

    id = Column(Integer, primary_key=True, index=True)
    planeamento_anual_id = Column(Integer, ForeignKey("planeamentos_clube_anuais.id"), nullable=False)
    ano = Column(Integer, nullable=False)
    mes = Column(Integer, nullable=False)
    titulo = Column(String, nullable=False)
    objetivos_mes = Column(Text, nullable=True)
    observacoes = Column(Text, nullable=True)
    estado = Column(String, default="rascunho", nullable=False)
    criado_em = Column(DateTime, default=datetime.now, nullable=False)
    atualizado_em = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)

    planeamento_anual = relationship("PlaneamentoClubeAnual", back_populates="planeamentos_mensais")
    planos_semanais = relationship(
        "PlanoSemanalClube",
        back_populates="planeamento_mensal",
        cascade="all, delete",
    )
    eventos = relationship(
        "EventoPlaneamentoClube",
        back_populates="planeamento_mensal",
        cascade="all, delete",
    )


class PlanoSemanalClube(Base):
    __tablename__ = "planos_semanais_clube"
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False, index=True)

    id = Column(Integer, primary_key=True, index=True)
    planeamento_mensal_id = Column(Integer, ForeignKey("planeamentos_clube_mensais.id"), nullable=False)
    titulo = Column(String, nullable=False)
    data_inicio = Column(Date, nullable=False)
    data_fim = Column(Date, nullable=False)
    observacoes = Column(Text, nullable=True)
    estado = Column(String, default="rascunho", nullable=False)
    ultima_sincronizacao_em = Column(DateTime, nullable=True)
    ultima_sincronizacao_por = Column(String, nullable=True)
    ultima_sincronizacao_resumo = Column(Text, nullable=True)
    criado_em = Column(DateTime, default=datetime.now, nullable=False)
    atualizado_em = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)

    planeamento_mensal = relationship("PlaneamentoClubeMensal", back_populates="planos_semanais")
    eventos = relationship(
        "EventoPlaneamentoClube",
        back_populates="plano_semanal",
        cascade="all, delete",
    )
    atribuicoes_espacos = relationship(
        "AtribuicaoEspacoSemanal",
        back_populates="plano_semanal",
        cascade="all, delete",
    )


class TipoEventoPlaneamentoClubeEnum(str, enum.Enum):
    treino_equipa = "treino_equipa"
    treino_fisico = "treino_fisico"
    treino_individual = "treino_individual"
    jogo = "jogo"
    atividade_extra = "atividade_extra"
    evento_clube = "evento_clube"
    folga = "folga"
    torneio = "torneio"
    viagem = "viagem"
    teste_fisico = "teste_fisico"
    outro = "outro"


class OrigemEventoPlaneamentoClubeEnum(str, enum.Enum):
    manual = "manual"
    jogo_existente = "jogo_existente"
    atividade_existente = "atividade_existente"


class EventoPlaneamentoClube(Base):
    __tablename__ = "eventos_planeamento_clube"

    id = Column(Integer, primary_key=True, index=True)
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False, index=True)
    tipo = Column(Enum(TipoEventoPlaneamentoClubeEnum), nullable=False)
    titulo = Column(String, nullable=False)
    descricao = Column(Text, nullable=True)
    data = Column(Date, nullable=False)
    hora_inicio = Column(String, nullable=True)
    hora_fim = Column(String, nullable=True)
    planeamento_anual_id = Column(Integer, ForeignKey("planeamentos_clube_anuais.id"), nullable=True)
    planeamento_mensal_id = Column(Integer, ForeignKey("planeamentos_clube_mensais.id"), nullable=True)
    plano_semanal_id = Column(Integer, ForeignKey("planos_semanais_clube.id"), nullable=True)
    macrociclo_id = Column(Integer, ForeignKey("macrociclos.id"), nullable=True)
    mesociclo_id = Column(Integer, ForeignKey("mesociclos.id"), nullable=True)
    microciclo_id = Column(Integer, ForeignKey("microciclos.id"), nullable=True)
    equipa_id = Column(Integer, ForeignKey("equipas.id"), nullable=True)
    espaco_id = Column(Integer, ForeignKey("espacos_treino.id"), nullable=True)
    treinador_id = Column(Integer, ForeignKey("treinadores.id"), nullable=True)
    jogo_id = Column(Integer, ForeignKey("jogos.id"), nullable=True)
    atividade_id = Column(Integer, ForeignKey("atividades.id"), nullable=True)
    aplica_a_todas_equipas = Column(Boolean, default=False, nullable=False)
    origem = Column(Enum(OrigemEventoPlaneamentoClubeEnum), nullable=False, default=OrigemEventoPlaneamentoClubeEnum.manual)
    observacoes = Column(Text, nullable=True)
    data_fim = Column(Date, nullable=True)
    serie_id = Column(String, nullable=True, index=True)
    recorrencia_frequencia = Column(String, nullable=True)
    recorrencia_intervalo = Column(Integer, nullable=True)
    ativo = Column(Boolean, default=True, nullable=False)
    alterado_por = Column(String, nullable=True)
    desativado_em = Column(DateTime, nullable=True)
    criado_em = Column(DateTime, default=datetime.now, nullable=False)
    atualizado_em = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)

    planeamento_anual = relationship("PlaneamentoClubeAnual", back_populates="eventos")
    planeamento_mensal = relationship("PlaneamentoClubeMensal", back_populates="eventos")
    plano_semanal = relationship("PlanoSemanalClube", back_populates="eventos")
    macrociclo = relationship("Macrociclo", back_populates="eventos_agenda")
    mesociclo = relationship("Mesociclo", back_populates="eventos_agenda")
    microciclo = relationship("Microciclo", back_populates="eventos_agenda")
    equipa = relationship("Equipa", backref="eventos_planeamento_clube")
    espaco = relationship("EspacoTreino", backref="eventos_planeamento_clube")
    treinador = relationship("Treinador", backref="eventos_planeamento_clube")
    jogo = relationship("Jogo", backref="eventos_planeamento_clube")
    atividade = relationship("Atividade", backref="eventos_planeamento_clube")
    equipas = relationship(
        "Equipa",
        secondary=evento_planeamento_clube_equipa,
        back_populates="eventos_globais",
    )
    atribuicoes_espaco = relationship(
        "AtribuicaoEspacoSemanal",
        back_populates="evento",
    )

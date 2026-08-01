import enum
from datetime import datetime

from sqlalchemy import Column, Date, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from database import Base


class TipoOcupacaoEspacoEnum(str, enum.Enum):
    treino_equipa = "treino_equipa"
    treino_individual = "treino_individual"
    jogo = "jogo"
    atividade = "atividade"
    bloqueio = "bloqueio"


class EstadoAtribuicaoEspacoEnum(str, enum.Enum):
    rascunho = "rascunho"
    publicado = "publicado"
    cancelado = "cancelado"


class OrigemAtribuicaoEspacoEnum(str, enum.Enum):
    manual = "manual"
    evento_global = "evento_global"


class AtribuicaoEspacoSemanal(Base):
    __tablename__ = "atribuicoes_espaco_semanais"
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False, index=True)

    id = Column(Integer, primary_key=True, index=True)
    plano_semanal_id = Column(Integer, ForeignKey("planos_semanais_clube.id"), nullable=False)
    espaco_id = Column(Integer, ForeignKey("espacos_treino.id"), nullable=False)
    equipa_id = Column(Integer, ForeignKey("equipas.id"), nullable=True)
    treinador_id = Column(Integer, ForeignKey("treinadores.id"), nullable=True)
    evento_id = Column(Integer, ForeignKey("eventos_planeamento_clube.id"), nullable=True)
    data = Column(Date, nullable=False)
    hora_inicio = Column(String, nullable=False)
    hora_fim = Column(String, nullable=False)
    tipo_ocupacao = Column(Enum(TipoOcupacaoEspacoEnum), nullable=False)
    estado = Column(Enum(EstadoAtribuicaoEspacoEnum), nullable=False, default=EstadoAtribuicaoEspacoEnum.rascunho)
    origem = Column(Enum(OrigemAtribuicaoEspacoEnum), nullable=False, default=OrigemAtribuicaoEspacoEnum.manual)
    observacoes = Column(Text, nullable=True)
    criado_em = Column(DateTime, default=datetime.now, nullable=False)
    atualizado_em = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)

    plano_semanal = relationship("PlanoSemanalClube", back_populates="atribuicoes_espacos")
    espaco = relationship("EspacoTreino", back_populates="atribuicoes_semanais")
    equipa = relationship("Equipa", backref="atribuicoes_espaco_semanais")
    treinador = relationship("Treinador", backref="atribuicoes_espaco_semanais")
    evento = relationship("EventoPlaneamentoClube", back_populates="atribuicoes_espaco")

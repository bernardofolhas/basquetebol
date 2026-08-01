# Importações necessárias do SQLAlchemy e Python
from datetime import datetime

from sqlalchemy import Column, Integer, String, Date, DateTime, Text, ForeignKey, Float, Boolean
from sqlalchemy.orm import relationship, backref
from database import Base


class PlaneamentoAnualEquipa(Base):
    """Enquadramento anual próprio da equipa, opcionalmente alinhado com o clube."""

    __tablename__ = "planeamentos_anuais_equipa"

    id = Column(Integer, primary_key=True, index=True)
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False, index=True)
    equipa_id = Column(Integer, ForeignKey("equipas.id", ondelete="CASCADE"), nullable=False, index=True)
    planeamento_clube_anual_id = Column(
        Integer,
        ForeignKey("planeamentos_clube_anuais.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    epoca = Column(String, nullable=False)
    titulo = Column(String, nullable=False)
    data_inicio = Column(Date, nullable=False)
    data_fim = Column(Date, nullable=False)
    objetivos_gerais = Column(Text, nullable=True)
    obj_tecnica_individual_ofensiva = Column(Text, nullable=True)
    obj_tecnica_individual_defensiva = Column(Text, nullable=True)
    obj_tatica_individual_ofensiva = Column(Text, nullable=True)
    obj_tatica_individual_defensiva = Column(Text, nullable=True)
    obj_tatica_coletiva_ofensiva = Column(Text, nullable=True)
    obj_tatica_coletiva_defensiva = Column(Text, nullable=True)
    obj_fisicos = Column(Text, nullable=True)
    obj_psicologicos = Column(Text, nullable=True)
    reflexao = Column(Text, nullable=True)
    estado = Column(String, nullable=False, default="rascunho", server_default="rascunho")
    criado_em = Column(DateTime, default=datetime.now, nullable=False)
    atualizado_em = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)

    equipa = relationship(
        "Equipa",
        backref=backref("planeamentos_anuais", cascade="all, delete", passive_deletes=True),
    )
    planeamento_clube_anual = relationship("PlaneamentoClubeAnual", backref="planeamentos_equipas")
    macrociclos = relationship(
        "Macrociclo",
        back_populates="planeamento_anual_equipa",
        cascade="all, delete",
    )


# ─────────────────────────────────────────
# MACROCICLO
# Bloco grande de planeamento (ex: Pré-época, Época Competitiva)
# Cada equipa pode ter vários macrociclos ao longo da época
# ─────────────────────────────────────────
class Macrociclo(Base):
    __tablename__ = "macrociclos"

    id = Column(Integer, primary_key=True, index=True)
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False, index=True)

    # Número automático do macro dentro da equipa (ex: Macro 1, Macro 2...)
    numero = Column(Integer, nullable=False)

    # Datas de início e fim do macrociclo
    data_inicio = Column(Date, nullable=False)
    data_fim = Column(Date, nullable=False)

    # Objetivos divididos pelas categorias táticas/técnicas
    obj_tecnica_individual_ofensiva = Column(Text, nullable=True)
    obj_tecnica_individual_defensiva = Column(Text, nullable=True)
    obj_tatica_individual_ofensiva = Column(Text, nullable=True)
    obj_tatica_individual_defensiva = Column(Text, nullable=True)
    obj_tatica_coletiva_ofensiva = Column(Text, nullable=True)
    obj_tatica_coletiva_defensiva = Column(Text, nullable=True)
    obj_fisicos = Column(Text, nullable=True)
    obj_psicologicos = Column(Text, nullable=True)

    # Reflexão do treinador no final do macrociclo
    reflexao = Column(Text, nullable=True)

    # Ligação à equipa — cada macrociclo pertence a uma equipa
    # ForeignKey cria a ligação entre tabelas
    equipa_id = Column(Integer, ForeignKey("equipas.id"), nullable=False)
    planeamento_anual_equipa_id = Column(
        Integer,
        ForeignKey("planeamentos_anuais_equipa.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # relationship permite aceder a equipa.macrociclos e macrociclo.equipa
    equipa = relationship("Equipa", backref="macrociclos")
    planeamento_anual_equipa = relationship("PlaneamentoAnualEquipa", back_populates="macrociclos")

    # Um macrociclo tem vários mesociclos
    mesociclos = relationship("Mesociclo", back_populates="macrociclo", cascade="all, delete")
    eventos_agenda = relationship(
        "EventoPlaneamentoClube",
        back_populates="macrociclo",
        cascade="all, delete",
    )
    # cascade="all, delete" significa: se apagarmos o macro, apagam-se também os mesos


# ─────────────────────────────────────────
# MESOCICLO
# Bloco médio de planeamento (geralmente um mês)
# Cada macrociclo tem vários mesociclos
# ─────────────────────────────────────────
class Mesociclo(Base):
    __tablename__ = "mesociclos"

    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False, index=True)

    id = Column(Integer, primary_key=True, index=True)

    # Número automático dentro do macrociclo
    numero = Column(Integer, nullable=False)

    data_inicio = Column(Date, nullable=False)
    data_fim = Column(Date, nullable=False)

    # Objetivos (mesmas categorias do macrociclo)
    obj_tecnica_individual_ofensiva = Column(Text, nullable=True)
    obj_tecnica_individual_defensiva = Column(Text, nullable=True)
    obj_tatica_individual_ofensiva = Column(Text, nullable=True)
    obj_tatica_individual_defensiva = Column(Text, nullable=True)
    obj_tatica_coletiva_ofensiva = Column(Text, nullable=True)
    obj_tatica_coletiva_defensiva = Column(Text, nullable=True)
    obj_fisicos = Column(Text, nullable=True)
    obj_psicologicos = Column(Text, nullable=True)

    reflexao = Column(Text, nullable=True)

    # Ligação ao macrociclo pai
    macrociclo_id = Column(Integer, ForeignKey("macrociclos.id"), nullable=False)
    macrociclo = relationship("Macrociclo", back_populates="mesociclos")

    # Um mesociclo tem vários microciclos
    microciclos = relationship("Microciclo", back_populates="mesociclo", cascade="all, delete")
    eventos_agenda = relationship(
        "EventoPlaneamentoClube",
        back_populates="mesociclo",
        cascade="all, delete",
    )


# ─────────────────────────────────────────
# MICROCICLO
# Bloco pequeno de planeamento (uma semana)
# Cada mesociclo tem vários microciclos
# ─────────────────────────────────────────
class Microciclo(Base):
    __tablename__ = "microciclos"

    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False, index=True)

    id = Column(Integer, primary_key=True, index=True)

    # Número automático dentro do mesociclo
    numero = Column(Integer, nullable=False)

    data_inicio = Column(Date, nullable=False)
    data_fim = Column(Date, nullable=False)

    # Tipo de microciclo (ex: Introdutório, Carga, Competitivo, Recuperação)
    tipo = Column(String, nullable=True)

    # Objetivos semanais
    obj_tecnica_individual_ofensiva = Column(Text, nullable=True)
    obj_tecnica_individual_defensiva = Column(Text, nullable=True)
    obj_tatica_individual_ofensiva = Column(Text, nullable=True)
    obj_tatica_individual_defensiva = Column(Text, nullable=True)
    obj_tatica_coletiva_ofensiva = Column(Text, nullable=True)
    obj_tatica_coletiva_defensiva = Column(Text, nullable=True)
    obj_fisicos = Column(Text, nullable=True)
    obj_psicologicos = Column(Text, nullable=True)

    reflexao = Column(Text, nullable=True)

    # Ligação ao mesociclo pai
    mesociclo_id = Column(Integer, ForeignKey("mesociclos.id"), nullable=False)
    mesociclo = relationship("Mesociclo", back_populates="microciclos")

    # Um microciclo tem vários dias de treino
    sessoes = relationship("SessaoTreino", back_populates="microciclo", cascade="all, delete")
    eventos_agenda = relationship(
        "EventoPlaneamentoClube",
        back_populates="microciclo",
        cascade="all, delete",
    )


# ─────────────────────────────────────────
# SESSÃO DE TREINO
# Um dia de treino dentro de um microciclo
# ─────────────────────────────────────────
class SessaoTreino(Base):
    __tablename__ = "sessoes_treino"

    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False, index=True)

    id = Column(Integer, primary_key=True, index=True)

    # Data e local do treino
    data = Column(Date, nullable=False)
    local = Column(String, nullable=True)
    hora_inicio = Column(String, nullable=True)
    hora_fim = Column(String, nullable=True)

    # Número sequencial do treino na época
    numero_treino = Column(Integer, nullable=True)

    # Volume em minutos e intensidade RPE (escala 1-10)
    volume_minutos = Column(Integer, nullable=True)
    intensidade_rpe = Column(Float, nullable=True)

    # Indica se é dia de jogo em vez de treino
    e_jogo = Column(Boolean, default=False)

    # Tempo dedicado a cada componente (em minutos)
    # A soma destes valores nunca pode exceder o volume_minutos
    min_tecnica_individual_ofensiva = Column(Integer, default=0)
    min_tecnica_individual_defensiva = Column(Integer, default=0)
    min_tatica_individual_ofensiva = Column(Integer, default=0)
    min_tatica_individual_defensiva = Column(Integer, default=0)
    min_tatica_coletiva_ofensiva = Column(Integer, default=0)
    min_tatica_coletiva_defensiva = Column(Integer, default=0)
    min_fisicos = Column(Integer, default=0)

    reflexao = Column(Text, nullable=True)
    origem = Column(String, nullable=False, default="manual")
    sincronizada = Column(Boolean, nullable=False, default=False)
    alterada_manual = Column(Boolean, nullable=False, default=False)
    ativa = Column(Boolean, nullable=False, default=True)
    estado = Column(String, nullable=False, default="planeada", server_default="planeada")

    # Ligação ao microciclo
    microciclo_id = Column(Integer, ForeignKey("microciclos.id"), nullable=False)
    plano_semanal_clube_id = Column(Integer, ForeignKey("planos_semanais_clube.id"), nullable=True)
    evento_planeamento_clube_id = Column(
        Integer,
        ForeignKey("eventos_planeamento_clube.id", ondelete="SET NULL"),
        nullable=True,
    )
    microciclo = relationship("Microciclo", back_populates="sessoes")
    plano_semanal_clube = relationship("PlanoSemanalClube", backref="sessoes_geradas")
    evento_planeamento_clube = relationship(
        "EventoPlaneamentoClube",
        backref=backref("sessoes_geradas"),
    )
    plano_treino = relationship(
        "PlanoTreino",
        back_populates="sessao",
        uselist=False,
        cascade="all, delete-orphan",
        single_parent=True,
    )

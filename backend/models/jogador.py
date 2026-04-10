from sqlalchemy import Column, Integer, String, Date, ForeignKey, Text
from sqlalchemy.orm import relationship
from database import Base


class Jogador(Base):
    __tablename__ = "jogadores"

    id = Column(Integer, primary_key=True, index=True)

    # Informações básicas
    nome = Column(String, nullable=False)
    data_nascimento = Column(Date, nullable=True)
    naturalidade = Column(String, nullable=True)
    morada = Column(String, nullable=True)
    numero_camisola = Column(Integer, nullable=True)
    posicao = Column(String, nullable=True)

    # Contactos do jogador
    telefone = Column(String, nullable=True)
    email = Column(String, nullable=True)

    # Contactos dos pais
    nome_pai = Column(String, nullable=True)
    telefone_pai = Column(String, nullable=True)
    email_pai = Column(String, nullable=True)
    nome_mae = Column(String, nullable=True)
    telefone_mae = Column(String, nullable=True)
    email_mae = Column(String, nullable=True)

    # Informações desportivas (a preencher pelo treinador)
    resumo_tecnico = Column(Text, nullable=True)
    objetivos_medio_prazo = Column(Text, nullable=True)
    objetivos_longo_prazo = Column(Text, nullable=True)

    # Equipa actual
    equipa_id = Column(Integer, ForeignKey("equipas.id"), nullable=True)
    equipa = relationship("Equipa", backref="jogadores")


class RegistoAntropometrico(Base):
    # Tabela separada para os registos antropométricos
    # Assim podemos guardar vários registos ao longo do tempo
    __tablename__ = "registos_antropometricos"

    id = Column(Integer, primary_key=True, index=True)
    jogador_id = Column(Integer, ForeignKey("jogadores.id"), nullable=False)
    data = Column(Date, nullable=False)
    altura = Column(String, nullable=True)   # em cm
    peso = Column(String, nullable=True)     # em kg
    envergadura = Column(String, nullable=True)  # em cm
    altura_sentado = Column(String, nullable=True)

    # Relação com o jogador
    jogador = relationship("Jogador", backref="registos_antropometricos")
from sqlalchemy import Column, Integer, String, Enum, ForeignKey
from sqlalchemy.orm import relationship
from database import Base
import enum


class EscalaoEnum(str, enum.Enum):
    sub8 = "Sub-8"
    sub10 = "Sub-10"
    sub12 = "Sub-12"
    sub14 = "Sub-14"
    sub16 = "Sub-16"
    sub18 = "Sub-18"
    senior = "Sénior"
    masters = "Masters"


class GeneroEnum(str, enum.Enum):
    masculino = "Masculino"
    feminino = "Feminino"
    misto = "Misto"


class Equipa(Base):
    __tablename__ = "equipas"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, nullable=False)
    escalao = Column(Enum(EscalaoEnum), nullable=False)
    genero = Column(Enum(GeneroEnum), nullable=False)
    seccionista = Column(String, nullable=True)

    # Relação com treinadores — uma equipa pode ter vários treinadores
    # Vamos definir isto melhor quando criarmos o modelo de treinador
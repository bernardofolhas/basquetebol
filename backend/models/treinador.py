from sqlalchemy import Column, Integer, String, Date, ForeignKey, Table
from sqlalchemy.orm import relationship
from database import Base


# Tabela de associação entre treinadores e equipas
# Um treinador pode ter várias equipas e uma equipa pode ter vários treinadores
# Isto chama-se uma relação "muitos para muitos"
treinador_equipa = Table(
    "treinador_equipa",
    Base.metadata,
    Column("treinador_id", Integer, ForeignKey("treinadores.id"), primary_key=True),
    Column("equipa_id", Integer, ForeignKey("equipas.id"), primary_key=True)
)


class Treinador(Base):
    __tablename__ = "treinadores"

    id = Column(Integer, primary_key=True, index=True)
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False, index=True)
    nome = Column(String, nullable=False)
    data_nascimento = Column(Date, nullable=True)
    morada = Column(String, nullable=True)
    telefone = Column(String, nullable=True)
    email = Column(String, nullable=True)
    numero_cedula = Column(String, nullable=True)
    numero_fpb = Column(String, nullable=True)
    funcao = Column(String, nullable=False, default="Treinador", server_default="Treinador")
    observacoes = Column(String, nullable=True)

    # Relação com equipas através da tabela de associação
    equipas = relationship("Equipa", secondary=treinador_equipa, backref="treinadores")

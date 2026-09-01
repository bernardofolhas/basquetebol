
from sqlalchemy import Column, Integer, String, Boolean, Enum, ForeignKey, Table
from sqlalchemy.orm import relationship
from database import Base
import enum


class PerfilEnum(str, enum.Enum):
    superadministrador = "superadministrador"
    administrador = "administrador"
    coordenador = "coordenador"
    treinador = "treinador"
    secretaria = "secretaria"
    staff = "staff"


# As contas de staff pertencem a uma ou mais equipas sem precisarem de ser
# registadas como treinadores. Isto limita o acesso ao contexto de trabalho
# que lhes foi atribuído pelo administrador do clube.
utilizador_staff_equipa = Table(
    "utilizador_staff_equipa",
    Base.metadata,
    Column("utilizador_id", Integer, ForeignKey("utilizadores.id", ondelete="CASCADE"), primary_key=True),
    Column("equipa_id", Integer, ForeignKey("equipas.id", ondelete="CASCADE"), primary_key=True),
)


class Utilizador(Base):
    __tablename__ = "utilizadores"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, nullable=False)
    username = Column(String, unique=True, nullable=False)
    email = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    perfil = Column(Enum(PerfilEnum), nullable=False)
    ativo = Column(Boolean, default=True)
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=True, index=True)
    deve_alterar_password = Column(Boolean, nullable=False, default=False)
    sessao_versao = Column(Integer, nullable=False, default=0, server_default="0")

    # Ligação opcional ao treinador
    treinador_id = Column(Integer, ForeignKey("treinadores.id"), nullable=True)

    # Relação ORM para aceder ao treinador associado
    treinador = relationship("Treinador", backref="utilizadores")
    clube = relationship("Clube", foreign_keys=[clube_id], backref="utilizadores")
    equipas_staff = relationship("Equipa", secondary=utilizador_staff_equipa, backref="utilizadores_staff")

from sqlalchemy import Column, Integer, String, Boolean, Enum
from database import Base
import enum

# Definimos os perfis possíveis como um enum
# Um enum é uma lista de valores fixos e válidos
class PerfilEnum(str, enum.Enum):
    administrador = "administrador"
    coordenador = "coordenador"
    treinador = "treinador"

class Utilizador(Base):
    # Nome da tabela na base de dados
    __tablename__ = "utilizadores"

    # Cada variável aqui é uma coluna da tabela
    id = Column(Integer, primary_key=True, index=True)
    # primary_key=True significa que é o identificador único de cada linha
    # index=True cria um índice para pesquisas mais rápidas

    nome = Column(String, nullable=False)
    # nullable=False significa que este campo é obrigatório

    username = Column(String, unique=True, nullable=False)
    # unique=True significa que não podem existir dois utilizadores com o mesmo username

    email = Column(String, unique=True, nullable=False)

    password_hash = Column(String, nullable=False)
    # Nunca guardamos a password diretamente — guardamos sempre uma versão encriptada

    perfil = Column(Enum(PerfilEnum), nullable=False)
    # O perfil só pode ser um dos três valores do PerfilEnum

    ativo = Column(Boolean, default=True)
    # Permite desativar um utilizador sem o apagar
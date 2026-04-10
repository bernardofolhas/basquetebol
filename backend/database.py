from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import os

# Carrega as variáveis do ficheiro .env
load_dotenv()

# Lê o endereço da base de dados do ficheiro .env
DATABASE_URL = os.getenv("DATABASE_URL")

# Cria o "motor" de ligação ao PostgreSQL
# É ele que sabe como falar com a base de dados
engine = create_engine(DATABASE_URL)

# Cria uma "fábrica" de sessões
# Uma sessão é uma conversa temporária com a base de dados
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base que todos os modelos vão herdar
# Um modelo é a representação em Python de uma tabela da base de dados
Base = declarative_base()

# Função que abre e fecha sessões automaticamente
# O "yield" faz com que a sessão seja fechada no final de cada pedido
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from database import SessionLocal, engine, Base
from logging_config import obter_logger
from models.utilizador import Utilizador, PerfilEnum
from auth import encriptar_password

logger = obter_logger(__name__)


def main():
    # Abre uma sessão com a base de dados
    db = SessionLocal()

    try:
        # Verifica se já existe um administrador
        # Não queremos criar duplicados
        admin_existente = db.query(Utilizador).filter(
            Utilizador.username == "admin"
        ).first()

        if admin_existente:
            logger.info("Já existe um utilizador admin.")
            return

        # Cria o utilizador administrador
        admin = Utilizador(
            nome="Administrador",
            username="admin",
            email="admin@basquetebol.pt",
            password_hash=encriptar_password("admin123"),
            perfil=PerfilEnum.administrador,
            ativo=True
        )

        # Adiciona à sessão e guarda na base de dados
        db.add(admin)
        db.commit()
        logger.info("Administrador criado com sucesso.")
        logger.warning(
            "ATENÇÃO: O utilizador 'admin' foi criado com a password padrão 'admin123'. "
            "Altera-a imediatamente em /admin/utilizadores antes de usar em produção."
        )
    finally:
        # Fecha a sessão
        db.close()


if __name__ == "__main__":
    main()

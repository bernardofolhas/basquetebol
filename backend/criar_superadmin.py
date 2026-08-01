"""Cria o primeiro superadministrador global sem credenciais predefinidas."""

import argparse
import getpass

from auth import encriptar_password
from database import SessionLocal
# Carrega as relações ORM usadas por Utilizador antes de configurar os mappers.
# O SQLAlchemy valida todas as relações na primeira query; este comando não
# arranca a aplicação, mas regista o mesmo conjunto de modelos que ela usa.
import models.atividade
import models.assiduidade
import models.atribuicao_espaco_semanal
import models.auditoria
import models.clube
import models.documento_jogador
import models.equipa
import models.espaco_agenda
import models.espaco_treino
import models.fisico
import models.historico_planeamento
import models.identidade_clube
import models.jogador
import models.jogo
import models.planeamento
import models.planeamento_clube
import models.playbook
import models.treinador
import models.treino
from models.utilizador import PerfilEnum, Utilizador


def main() -> None:
    parser = argparse.ArgumentParser(description="Criar um superadministrador global")
    parser.add_argument("--username", required=True)
    parser.add_argument("--nome", required=True)
    parser.add_argument("--email", required=True)
    args = parser.parse_args()
    password = getpass.getpass("Password (mínimo 12 caracteres): ")
    if len(password) < 12:
        raise SystemExit("A password deve ter pelo menos 12 caracteres.")

    db = SessionLocal()
    try:
        existe = db.query(Utilizador).execution_options(ignorar_clube=True).filter(
            (Utilizador.username == args.username) | (Utilizador.email == args.email)
        ).first()
        if existe:
            raise SystemExit("Já existe uma conta com esse username ou email.")
        db.add(Utilizador(
            nome=args.nome, username=args.username, email=args.email,
            password_hash=encriptar_password(password), perfil=PerfilEnum.superadministrador,
            ativo=True, clube_id=None, deve_alterar_password=False,
        ))
        db.commit()
        print("Superadministrador criado com sucesso.")
    finally:
        db.close()


if __name__ == "__main__":
    main()

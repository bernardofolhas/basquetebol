from database import SessionLocal, engine, Base
from models.utilizador import Utilizador, PerfilEnum
from auth import encriptar_password

# Abre uma sessão com a base de dados
db = SessionLocal()

# Verifica se já existe um administrador
# Não queremos criar duplicados
admin_existente = db.query(Utilizador).filter(
    Utilizador.username == "admin"
).first()

if admin_existente:
    print("Já existe um utilizador admin!")
else:
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
    print("Administrador criado com sucesso!")

# Fecha a sessão
db.close()
from uuid import uuid4

from database import SessionLocal
from models.equipa import Equipa
from models.utilizador import PerfilEnum, Utilizador


def test_criacao_fisioterapeuta_exige_equipa(client_admin):
    sufixo = uuid4().hex[:8]
    formulario = client_admin.get("/admin/utilizadores/novo")
    assert formulario.status_code == 200
    assert 'value="fisioterapeuta"' in formulario.text
    assert "Acesso de fisioterapeuta" in formulario.text

    resposta = client_admin.post(
        "/admin/utilizadores/novo",
        data={
            "nome": "Fisioterapeuta sem equipa",
            "username": f"fisio_sem_{sufixo}",
            "email": f"fisio-sem-{sufixo}@example.test",
            "password": "FisioTeste123!",
            "perfil": "fisioterapeuta",
        },
        follow_redirects=False,
    )

    assert resposta.status_code == 200
    assert "Seleciona pelo menos uma equipa" in resposta.text


def test_fisioterapeuta_tem_primeiro_acesso_e_dashboard_proprio(client_admin):
    db = SessionLocal()
    conta_id = None
    try:
        equipa = db.query(Equipa).order_by(Equipa.id).first()
        assert equipa is not None
        sufixo = uuid4().hex[:8]
        username = f"fisio_{sufixo}"
        password = "FisioTeste123!"
        resposta = client_admin.post(
            "/admin/utilizadores/novo",
            data={
                "nome": "Fisioterapeuta de teste",
                "username": username,
                "email": f"{username}@example.test",
                "password": password,
                "perfil": "fisioterapeuta",
                "equipa_ids": str(equipa.id),
            },
            follow_redirects=False,
        )
        assert resposta.status_code == 303

        conta = db.query(Utilizador).filter(Utilizador.username == username).one()
        conta_id = conta.id
        assert conta.perfil == PerfilEnum.fisioterapeuta
        assert conta.deve_alterar_password is True
        assert [item.id for item in conta.equipas_staff] == [equipa.id]

        login = client_admin.post(
            "/login-form",
            data={"username": username, "password": password},
            follow_redirects=False,
        )
        assert login.status_code == 303
        assert login.headers["location"] == "/dashboard"
        primeiro_acesso = client_admin.get("/dashboard", follow_redirects=False)
        assert primeiro_acesso.status_code == 303
        assert primeiro_acesso.headers["location"] == "/minha-conta"

        conta.deve_alterar_password = False
        db.commit()
        dashboard = client_admin.get("/dashboard")
        assert dashboard.status_code == 200
        assert "Dashboard do fisioterapeuta" in dashboard.text
        assert equipa.nome in dashboard.text
        assert "Abrir questionários" in dashboard.text
    finally:
        if conta_id:
            conta = db.query(Utilizador).filter(Utilizador.id == conta_id).first()
            if conta:
                conta.equipas_staff = []
                db.delete(conta)
                db.commit()
        db.close()

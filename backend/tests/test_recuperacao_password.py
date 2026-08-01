import re
from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from auth import encriptar_password
from database import SessionLocal
from limiter import limiter
from main import app
from models.auditoria import RegistoAuditoria
from models.clube import Clube
from models.recuperacao_password import TokenRecuperacaoPassword
from models.utilizador import PerfilEnum, Utilizador
from services.recuperacao_password_service import criar_token_recuperacao
from testsupport import TestClient


@pytest.fixture
def contexto_recuperacao(monkeypatch):
    sufixo = uuid4().hex[:10]
    db = SessionLocal()
    clube = Clube(
        nome_oficial=f"Clube recuperação {sufixo}", nome_curto=f"CR {sufixo}",
        identificador=f"recuperacao-{sufixo}", cor_principal="#c2410c",
        cor_secundaria="#1f2937", cor_destaque="#0ea5e9",
    )
    outro = Clube(
        nome_oficial=f"Outro recuperação {sufixo}", nome_curto=f"OR {sufixo}",
        identificador=f"outra-recuperacao-{sufixo}", cor_principal="#334155",
        cor_secundaria="#0f172a", cor_destaque="#64748b",
    )
    db.add_all([clube, outro])
    db.flush()
    password = "Inicial2026Segura"
    admin = Utilizador(
        clube_id=clube.id, nome="Administrador recuperação", username=f"admin-rec-{sufixo}",
        email=f"admin-rec-{sufixo}@example.test", password_hash=encriptar_password(password),
        perfil=PerfilEnum.administrador, ativo=True,
    )
    alvo = Utilizador(
        clube_id=clube.id, nome="Treinador recuperação", username=f"coach-rec-{sufixo}",
        email=f"coach-rec-{sufixo}@example.test", password_hash=encriptar_password(password),
        perfil=PerfilEnum.treinador, ativo=True,
    )
    externo = Utilizador(
        clube_id=outro.id, nome="Utilizador externo", username=f"externo-rec-{sufixo}",
        email=f"externo-rec-{sufixo}@example.test", password_hash=encriptar_password(password),
        perfil=PerfilEnum.treinador, ativo=True,
    )
    superadmin = Utilizador(
        clube_id=None, nome="Superadministrador recuperação", username=f"super-rec-{sufixo}",
        email=f"super-rec-{sufixo}@example.test", password_hash=encriptar_password(password),
        perfil=PerfilEnum.superadministrador, ativo=True,
    )
    db.add_all([admin, alvo, externo, superadmin])
    db.commit()
    emails = []

    def guardar_email(destinatario, assunto, texto):
        emails.append({"destinatario": destinatario, "assunto": assunto, "texto": texto})
        return True

    monkeypatch.setattr("routers.auth_web.enviar_email", guardar_email)
    limiter._storage.reset()
    yield {"db": db, "clube": clube, "outro": outro, "admin": admin, "alvo": alvo,
           "externo": externo, "superadmin": superadmin, "password": password, "emails": emails}
    db.rollback()
    db.query(TokenRecuperacaoPassword).execution_options(ignorar_clube=True).filter(
        TokenRecuperacaoPassword.utilizador_id.in_([admin.id, alvo.id, externo.id, superadmin.id])
    ).delete(synchronize_session=False)
    db.query(RegistoAuditoria).execution_options(ignorar_clube=True).filter(
        RegistoAuditoria.utilizador_id.in_([admin.id, alvo.id, externo.id, superadmin.id])
    ).delete(synchronize_session=False)
    db.query(Utilizador).execution_options(ignorar_clube=True).filter(
        Utilizador.id.in_([admin.id, alvo.id, externo.id, superadmin.id])
    ).delete(synchronize_session=False)
    db.query(Clube).filter(Clube.id.in_([clube.id, outro.id])).delete(synchronize_session=False)
    db.commit()
    db.close()
    limiter._storage.reset()


def _login(cliente, utilizador, password):
    resposta = cliente.post("/login-form", data={"username": utilizador.username, "password": password}, follow_redirects=False)
    assert resposta.status_code == 303


def _token_do_ultimo_email(emails):
    correspondencia = re.search(r"/redefinir-password/([^\s]+)", emails[-1]["texto"])
    assert correspondencia
    return correspondencia.group(1)


def test_recuperacao_email_tokens_politica_e_sessoes(contexto_recuperacao):
    dados = contexto_recuperacao
    cliente = TestClient(app)
    cliente.get("/recuperar-password")
    existente = cliente.post("/recuperar-password", data={"identificador": dados["alvo"].email})
    inexistente = cliente.post("/recuperar-password", data={"identificador": "nao-existe@example.test"})
    mensagem = "Se os dados corresponderem a uma conta ativa"
    assert existente.status_code == inexistente.status_code == 200
    assert mensagem in existente.text and mensagem in inexistente.text
    assert len(dados["emails"]) == 1
    token = _token_do_ultimo_email(dados["emails"])

    pagina = cliente.get(f"/redefinir-password/{token}")
    assert pagina.status_code == 200 and "Definir nova palavra-passe" in pagina.text
    invalida = cliente.post(f"/redefinir-password/{token}", data={
        "password_nova": "curta", "password_confirmar": "curta",
    })
    assert invalida.status_code == 422
    assert "pelo menos 10 caracteres" in invalida.text

    sessao_antiga = TestClient(app)
    _login(sessao_antiga, dados["alvo"], dados["password"])
    nova_password = "NovaPassword2026"
    concluida = cliente.post(f"/redefinir-password/{token}", data={
        "password_nova": nova_password, "password_confirmar": nova_password,
    })
    assert concluida.status_code == 200
    assert "Palavra-passe alterada" in concluida.text
    assert cliente.get(f"/redefinir-password/{token}").text.count("inválida") >= 1
    assert cliente.post(f"/redefinir-password/{token}", data={
        "password_nova": "OutraPassword2027", "password_confirmar": "OutraPassword2027",
    }).status_code == 400
    assert sessao_antiga.get("/dashboard", follow_redirects=False).status_code in (302, 303)
    assert len(dados["emails"]) == 2

    token_expirado, registo = criar_token_recuperacao(dados["db"], dados["alvo"])
    registo.expira_em = datetime.now() - timedelta(seconds=1)
    dados["db"].commit()
    assert "inválida" in cliente.get(f"/redefinir-password/{token_expirado}").text


def test_limite_de_pedidos_de_recuperacao(contexto_recuperacao):
    cliente = TestClient(app)
    cliente.get("/recuperar-password")
    respostas = [cliente.post("/recuperar-password", data={"identificador": f"ausente-{i}@example.test"}) for i in range(6)]
    assert all(resposta.status_code == 200 for resposta in respostas[:5])
    assert respostas[5].status_code == 429


def test_recuperacao_administrativa_e_isolamento(contexto_recuperacao):
    dados = contexto_recuperacao
    admin = TestClient(app)
    _login(admin, dados["admin"], dados["password"])
    bloqueio = admin.post(
        f"/admin/utilizadores/{dados['externo'].id}/recuperacao-temporaria",
        follow_redirects=False,
    )
    assert bloqueio.status_code == 303
    assert bloqueio.headers["location"] == "/admin/utilizadores"

    pagina = admin.post(f"/admin/utilizadores/{dados['alvo'].id}/recuperacao-temporaria")
    assert pagina.status_code == 200
    correspondencia = re.search(r"/acesso-temporario/([A-Za-z0-9_-]+)", pagina.text)
    assert correspondencia
    token = correspondencia.group(1)
    utilizador = TestClient(app)
    confirmacao = utilizador.get(f"/acesso-temporario/{token}")
    assert confirmacao.status_code == 200 and "Confirmar acesso temporário" in confirmacao.text
    entrada = utilizador.post(f"/acesso-temporario/{token}", follow_redirects=False)
    assert entrada.status_code == 303 and entrada.headers["location"] == "/minha-conta"
    conta = utilizador.get("/minha-conta")
    assert "O acesso é temporário" in conta.text
    nova_sessao = TestClient(app)
    assert nova_sessao.post(f"/acesso-temporario/{token}", follow_redirects=False).headers["location"] == "/login"
    nova = "TemporariaNova2026"
    resposta = utilizador.post("/minha-conta/alterar-password", data={
        "password_nova": nova, "password_confirmar": nova,
    }, follow_redirects=False)
    assert resposta.status_code == 303 and resposta.headers["location"] == "/login"
    _login(TestClient(app), dados["alvo"], nova)
    auditoria = dados["db"].query(RegistoAuditoria).execution_options(ignorar_clube=True).filter(
        RegistoAuditoria.acao == "gerar_acesso_temporario",
        RegistoAuditoria.entidade_id == dados["alvo"].id,
    ).first()
    assert auditoria and auditoria.utilizador_id == dados["admin"].id


def test_superadministrador_recupera_conta_de_qualquer_clube(contexto_recuperacao):
    dados = contexto_recuperacao
    superadmin = TestClient(app)
    _login(superadmin, dados["superadmin"], dados["password"])

    pagina = superadmin.post(
        f"/superadmin/utilizadores/{dados['externo'].id}/recuperacao-temporaria"
    )
    assert pagina.status_code == 200
    assert dados["externo"].nome in pagina.text
    assert dados["superadmin"].nome in pagina.text
    assert "/acesso-temporario/" in pagina.text

    propria = superadmin.post(
        f"/superadmin/utilizadores/{dados['superadmin'].id}/recuperacao-temporaria",
        follow_redirects=False,
    )
    assert propria.status_code == 303
    assert propria.headers["location"] == "/superadmin/utilizadores"

from uuid import uuid4

from auth import encriptar_password
from clube_contexto import definir_clube_atual, repor_clube_atual
from database import SessionLocal
from main import app
from models.clube import Clube, EstadoClubeEnum
from models.equipa import Equipa, EscalaoEnum, GeneroEnum
from models.identidade_clube import IdentidadeClube
from models.utilizador import PerfilEnum, Utilizador
from services.identidade_clube_service import obter_identidade_clube
from testsupport import TestClient


def _novo_clube(db, sufixo: str, estado=EstadoClubeEnum.ativo):
    clube = Clube(
        nome_oficial=f"Clube Teste {sufixo}", nome_curto=f"CT {sufixo}",
        identificador=f"teste-{sufixo}", cor_principal="#123456",
        cor_secundaria="#ffffff", cor_destaque="#f59e0b", estado=estado,
    )
    db.add(clube)
    db.flush()
    db.add(IdentidadeClube(
        clube_id=clube.id, nome_oficial=clube.nome_oficial, nome_curto=clube.nome_curto,
        cor_principal=clube.cor_principal, cor_secundaria=clube.cor_secundaria,
        cor_destaque=clube.cor_destaque,
    ))
    return clube


def test_consultas_e_ids_ficam_isolados_por_clube():
    db = SessionLocal()
    sufixo = uuid4().hex[:10]
    clube_a = clube_b = None
    try:
        clube_a = _novo_clube(db, f"a-{sufixo}")
        clube_b = _novo_clube(db, f"b-{sufixo}")
        db.commit()
        token = definir_clube_atual(clube_b.id)
        try:
            equipa = Equipa(nome="Equipa privada", escalao=EscalaoEnum.sub18, genero=GeneroEnum.feminino)
            db.add(equipa)
            db.commit()
            equipa_id = equipa.id
        finally:
            repor_clube_atual(token)
        token = definir_clube_atual(clube_a.id)
        try:
            assert db.query(Equipa).filter(Equipa.id == equipa_id).first() is None
        finally:
            repor_clube_atual(token)
    finally:
        db.rollback()
        if clube_a and clube_b:
            db.query(Equipa).execution_options(ignorar_clube=True).filter(Equipa.clube_id.in_([clube_a.id, clube_b.id])).delete(synchronize_session=False)
            db.query(IdentidadeClube).execution_options(ignorar_clube=True).filter(IdentidadeClube.clube_id.in_([clube_a.id, clube_b.id])).delete(synchronize_session=False)
            db.query(Clube).filter(Clube.id.in_([clube_a.id, clube_b.id])).delete(synchronize_session=False)
            db.commit()
        db.close()


def test_identidade_visual_respeita_contexto_do_clube():
    db = SessionLocal()
    sufixo = uuid4().hex[:10]
    clube = None
    try:
        clube = _novo_clube(db, sufixo)
        db.commit()
        token = definir_clube_atual(clube.id)
        try:
            identidade = obter_identidade_clube(db)
            assert identidade["nome_oficial"] == clube.nome_oficial
            assert identidade["cor_principal"] == "#123456"
        finally:
            repor_clube_atual(token)
    finally:
        if clube:
            db.query(IdentidadeClube).execution_options(ignorar_clube=True).filter(IdentidadeClube.clube_id == clube.id).delete()
            db.delete(clube)
            db.commit()
        db.close()


def test_clube_suspenso_bloqueia_operacao_normal():
    db = SessionLocal()
    sufixo = uuid4().hex[:10]
    clube = utilizador = None
    try:
        clube = _novo_clube(db, sufixo, EstadoClubeEnum.suspenso)
        utilizador = Utilizador(
            nome="Admin suspenso", username=f"susp-{sufixo}", email=f"susp-{sufixo}@example.test",
            password_hash=encriptar_password("password-segura"), perfil=PerfilEnum.administrador,
            clube_id=clube.id, ativo=True,
        )
        db.add(utilizador)
        db.commit()
        cliente = TestClient(app)
        resposta = cliente.post("/login-form", data={"username": utilizador.username, "password": "password-segura"}, follow_redirects=False)
        assert resposta.status_code == 303
        assert cliente.get("/dashboard").status_code == 423
    finally:
        if utilizador:
            db.query(Utilizador).execution_options(ignorar_clube=True).filter(Utilizador.id == utilizador.id).delete()
        if clube:
            db.query(IdentidadeClube).execution_options(ignorar_clube=True).filter(IdentidadeClube.clube_id == clube.id).delete()
            db.delete(clube)
        db.commit()
        db.close()

from datetime import date
from uuid import uuid4

import pytest

from auth import encriptar_password
from database import SessionLocal
from main import app
from models.clube import Clube
from models.equipa import Equipa, EscalaoEnum, GeneroEnum
from models.jogador import Jogador
from models.planeamento_clube import PlaneamentoClubeAnual, PlaneamentoClubeMensal, PlanoSemanalClube
from models.utilizador import PerfilEnum, Utilizador
from testsupport import TestClient


@pytest.fixture
def contexto_permissoes():
    sufixo = uuid4().hex[:10]
    db = SessionLocal()
    try:
        clube = Clube(
            nome_oficial=f"Clube Permissões {sufixo}",
            nome_curto=f"CP {sufixo}",
            identificador=f"permissoes-{sufixo}",
            cor_principal="#c2410c",
            cor_secundaria="#1f2937",
            cor_destaque="#0ea5e9",
        )
        outro_clube = Clube(
            nome_oficial=f"Outro Clube {sufixo}",
            nome_curto=f"OC {sufixo}",
            identificador=f"outro-{sufixo}",
            cor_principal="#334155",
            cor_secundaria="#0f172a",
            cor_destaque="#64748b",
        )
        db.add_all([clube, outro_clube])
        db.flush()

        credenciais = {}
        for perfil in (PerfilEnum.administrador, PerfilEnum.treinador, PerfilEnum.secretaria):
            username = f"{perfil.value}-{sufixo}"
            password = f"Teste-{sufixo}!"
            db.add(Utilizador(
                nome=f"Utilizador {perfil.value}",
                username=username,
                email=f"{username}@example.test",
                password_hash=encriptar_password(password),
                perfil=perfil,
                clube_id=clube.id,
                ativo=True,
            ))
            credenciais[perfil.value] = {"username": username, "password": password}

        equipa = Equipa(
            nome=f"Equipa Operacional {sufixo}",
            escalao=EscalaoEnum.sub18,
            genero=GeneroEnum.feminino,
            clube_id=clube.id,
        )
        anual_externo = PlaneamentoClubeAnual(
            clube_id=outro_clube.id,
            epoca="2026/2027",
            titulo=f"Planeamento externo {sufixo}",
            data_inicio=date(2026, 9, 1),
            data_fim=date(2027, 6, 30),
            ativo=True,
        )
        db.add_all([equipa, anual_externo])
        db.flush()
        jogador = Jogador(
            nome=f"Atleta Administrativa {sufixo}",
            clube_id=clube.id,
            equipa_id=equipa.id,
            inscricao_estado="pendente",
        )
        db.add(jogador)
        mensal_externo = PlaneamentoClubeMensal(
            clube_id=outro_clube.id,
            planeamento_anual_id=anual_externo.id,
            ano=2026,
            mes=9,
            titulo=f"Mensal externo {sufixo}",
            estado="rascunho",
        )
        db.add(mensal_externo)
        db.commit()

        yield {
            "clube_id": clube.id,
            "outro_clube_id": outro_clube.id,
            "equipa_id": equipa.id,
            "jogador_id": jogador.id,
            "mensal_externo_id": mensal_externo.id,
            "credenciais": credenciais,
            "sufixo": sufixo,
        }
    finally:
        db.rollback()
        clube_ids = []
        if "clube" in locals() and clube.id:
            clube_ids.append(clube.id)
        if "outro_clube" in locals() and outro_clube.id:
            clube_ids.append(outro_clube.id)
        if clube_ids:
            for modelo in (PlanoSemanalClube, PlaneamentoClubeMensal, PlaneamentoClubeAnual, Jogador, Equipa, Utilizador):
                db.query(modelo).execution_options(ignorar_clube=True).filter(
                    modelo.clube_id.in_(clube_ids)
                ).delete(synchronize_session=False)
            db.query(Clube).filter(Clube.id.in_(clube_ids)).delete(synchronize_session=False)
            db.commit()
        db.close()


def _cliente_autenticado(credenciais: dict) -> TestClient:
    cliente = TestClient(app)
    resposta = cliente.post("/login-form", data=credenciais, follow_redirects=False)
    assert resposta.status_code == 303
    return cliente


def test_administrador_gere_e_exporta_planeamento_mensal_e_semanal(contexto_permissoes):
    dados = contexto_permissoes
    cliente = _cliente_autenticado(dados["credenciais"]["administrador"])
    titulo_anual = f"Anual permissões {dados['sufixo']}"
    titulo_mensal = f"Mensal permissões {dados['sufixo']}"
    titulo_semanal = f"Semanal permissões {dados['sufixo']}"

    resposta = cliente.post("/planeamento-clube/anual/novo", data={
        "epoca": "2026/2027",
        "titulo": titulo_anual,
        "data_inicio": "2026-09-01",
        "data_fim": "2027-06-30",
        "objetivos_gerais": "Objetivos de teste",
        "observacoes": "",
        "ativo": "true",
    }, follow_redirects=False)
    assert resposta.status_code == 303

    db = SessionLocal()
    try:
        anual = db.query(PlaneamentoClubeAnual).execution_options(ignorar_clube=True).filter(
            PlaneamentoClubeAnual.titulo == titulo_anual
        ).one()
        anual_id = anual.id
    finally:
        db.close()

    resposta = cliente.post(f"/planeamento-clube/anual/{anual_id}/mensal/novo", data={
        "ano": "2026",
        "mes": "9",
        "titulo": titulo_mensal,
        "objetivos_mes": "Objetivos mensais",
        "observacoes": "",
        "estado": "rascunho",
    }, follow_redirects=False)
    assert resposta.status_code == 303

    db = SessionLocal()
    try:
        mensal = db.query(PlaneamentoClubeMensal).execution_options(ignorar_clube=True).filter(
            PlaneamentoClubeMensal.titulo == titulo_mensal
        ).one()
        mensal_id = mensal.id
    finally:
        db.close()

    resposta = cliente.post(f"/planeamento-clube/mensal/{mensal_id}/semanal/novo", data={
        "titulo": titulo_semanal,
        "data_inicio": "2026-09-07",
        "data_fim": "2026-09-13",
        "observacoes": "",
        "estado": "rascunho",
    }, follow_redirects=False)
    assert resposta.status_code == 303

    db = SessionLocal()
    try:
        semanal = db.query(PlanoSemanalClube).execution_options(ignorar_clube=True).filter(
            PlanoSemanalClube.titulo == titulo_semanal
        ).one()
        semanal_id = semanal.id
    finally:
        db.close()

    assert cliente.get(f"/planeamento-clube/mensal/{mensal_id}/pdf").headers["content-type"].startswith("application/pdf")
    assert cliente.get(f"/planeamento-clube/semanal/{semanal_id}/pdf").headers["content-type"].startswith("application/pdf")

    resposta = cliente.post(f"/planeamento-clube/mensal/{mensal_id}/editar", data={
        "ano": "2026", "mes": "9", "titulo": f"{titulo_mensal} editado",
        "objetivos_mes": "Revistos", "observacoes": "", "estado": "ativo",
    }, follow_redirects=False)
    assert resposta.status_code == 303
    resposta = cliente.post(f"/planeamento-clube/semanal/{semanal_id}/editar", data={
        "titulo": f"{titulo_semanal} editado", "data_inicio": "2026-09-07",
        "data_fim": "2026-09-13", "observacoes": "", "estado": "ativo",
    }, follow_redirects=False)
    assert resposta.status_code == 303

    assert cliente.post(f"/planeamento-clube/semanal/{semanal_id}/eliminar", follow_redirects=False).status_code == 303
    assert cliente.post(f"/planeamento-clube/mensal/{mensal_id}/eliminar", follow_redirects=False).status_code == 303


def test_interface_e_urls_respeitam_os_perfis(contexto_permissoes):
    dados = contexto_permissoes
    treinador = _cliente_autenticado(dados["credenciais"]["treinador"])
    pagina_treinador = treinador.get("/minha-conta")
    assert pagina_treinador.status_code == 200
    assert "/planeamento-clube/anual" not in pagina_treinador.text
    assert "/admin/utilizadores" not in pagina_treinador.text
    bloqueio_treinador = treinador.get("/planeamento-clube/mensal", follow_redirects=False)
    assert bloqueio_treinador.status_code == 302
    assert bloqueio_treinador.headers["location"] == "/dashboard"

    secretaria = _cliente_autenticado(dados["credenciais"]["secretaria"])
    pagina_secretaria = secretaria.get("/secretaria/pendencias")
    assert pagina_secretaria.status_code == 200
    assert 'href="/planeamento-clube/semanal"' in pagina_secretaria.text
    assert 'href="/planeamento-clube/espacos"' in pagina_secretaria.text
    assert 'action="/pesquisa"' not in pagina_secretaria.text
    assert 'href="/calendario"' not in pagina_secretaria.text
    bloqueio_secretaria = secretaria.get("/planeamento-clube/semanal", follow_redirects=False)
    assert bloqueio_secretaria.status_code == 200
    assert "/planeamento-clube/semanal/novo" not in bloqueio_secretaria.text
    assert secretaria.get("/biblioteca", follow_redirects=False).headers["location"] == "/dashboard"
    processo = secretaria.get(f"/jogadores/{dados['jogador_id']}")
    assert processo.status_code == 200
    assert "Processo administrativo" in processo.text
    assert "Ficha de evolução" not in processo.text
    assert "/fisico/" not in processo.text


def test_painel_equipa_simplificado_e_isolamento_entre_clubes(contexto_permissoes):
    dados = contexto_permissoes
    administrador = _cliente_autenticado(dados["credenciais"]["administrador"])
    entrada = administrador.get(f"/equipas/{dados['equipa_id']}", follow_redirects=False)
    assert entrada.status_code == 303
    assert entrada.headers["location"] == f"/equipas/{dados['equipa_id']}/resumo"
    painel = administrador.get(f"/equipas/{dados['equipa_id']}/resumo")
    assert painel.status_code == 200
    assert "Plantel associado à equipa" not in painel.text
    assert "Equipa técnica atualmente ligada" not in painel.text
    assert "Eventos Globais" not in painel.text
    assert "Atalhos" not in painel.text
    assert "Próxima atividade" in painel.text
    assert f'data-dashboard-key="resumo-equipa-{dados["equipa_id"]}"' in painel.text
    assert 'data-dashboard-widget="proxima-atividade"' in painel.text
    assert 'data-dashboard-widget="informacao-equipa"' in painel.text
    assert 'data-dashboard-widget="logistica-semanal"' in painel.text

    externo = administrador.get(
        f"/planeamento-clube/mensal/{dados['mensal_externo_id']}",
        follow_redirects=False,
    )
    assert externo.status_code in (303, 307)
    assert externo.headers["location"] == "/planeamento-clube/anual"

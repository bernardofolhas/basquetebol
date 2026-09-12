from datetime import date
from uuid import uuid4

from auth import encriptar_password
from database import SessionLocal
from main import app
from models.clube import Clube
from models.equipa import Equipa, EscalaoEnum, GeneroEnum
from models.planeamento import Macrociclo, Mesociclo, Microciclo, PlaneamentoAnualEquipa, SessaoTreino
from models.planeamento_clube import PlaneamentoClubeAnual
from models.treinador import Treinador
from models.treino import PlanoTreino
from models.utilizador import PerfilEnum, Utilizador
from testsupport import TestClient


def test_treinador_gere_anual_da_equipa_e_hierarquia_integrada():
    sufixo = uuid4().hex[:10]
    db = SessionLocal()
    cliente = TestClient(app)
    clube = Clube(
        nome_oficial=f"Clube anual {sufixo}", nome_curto=f"CA {sufixo}",
        identificador=f"anual-{sufixo}", cor_principal="#c2410c",
        cor_secundaria="#1f2937", cor_destaque="#0ea5e9",
    )
    outro_clube = Clube(
        nome_oficial=f"Outro anual {sufixo}", nome_curto=f"OA {sufixo}",
        identificador=f"outro-anual-{sufixo}", cor_principal="#334155",
        cor_secundaria="#0f172a", cor_destaque="#64748b",
    )
    db.add_all([clube, outro_clube])
    db.flush()
    equipa = Equipa(
        clube_id=clube.id, nome=f"Equipa anual {sufixo}",
        escalao=EscalaoEnum.sub18, genero=GeneroEnum.feminino,
    )
    equipa_externa = Equipa(
        clube_id=outro_clube.id, nome=f"Equipa externa {sufixo}",
        escalao=EscalaoEnum.sub16, genero=GeneroEnum.masculino,
    )
    treinador = Treinador(clube_id=clube.id, nome=f"Treinador {sufixo}")
    anual_clube = PlaneamentoClubeAnual(
        clube_id=clube.id, epoca="2026/2027", titulo=f"Plano clube {sufixo}",
        data_inicio=date(2026, 7, 1), data_fim=date(2027, 6, 30),
        objetivos_gerais="Identidade comum do clube", ativo=True,
    )
    db.add_all([equipa, equipa_externa, treinador, anual_clube])
    db.flush()
    treinador.equipas.append(equipa)
    password = f"Teste-{sufixo}!"
    utilizador = Utilizador(
        clube_id=clube.id, treinador_id=treinador.id, nome=f"Coach {sufixo}",
        username=f"coach-anual-{sufixo}", email=f"coach-anual-{sufixo}@example.test",
        password_hash=encriptar_password(password), perfil=PerfilEnum.treinador, ativo=True,
    )
    db.add(utilizador)
    db.commit()

    try:
        resposta = cliente.post("/login-form", data={
            "username": utilizador.username, "password": password,
        }, follow_redirects=False)
        assert resposta.status_code == 303

        resposta = cliente.post(f"/planeamento/equipas/{equipa.id}/anuais/novo", data={
            "epoca": "2026/2027", "titulo": "Época da equipa",
            "data_inicio": "2026-07-01", "data_fim": "2027-06-30",
            "planeamento_clube_anual_id": str(anual_clube.id), "estado": "ativo",
            "objetivos_gerais": "", "obj_tecnica_individual_ofensiva": "Finalização",
        }, follow_redirects=False)
        assert resposta.status_code == 303

        db.expire_all()
        anual_equipa = db.query(PlaneamentoAnualEquipa).execution_options(ignorar_clube=True).filter(
            PlaneamentoAnualEquipa.equipa_id == equipa.id,
        ).one()
        assert anual_equipa.planeamento_clube_anual_id == anual_clube.id
        assert anual_equipa.objetivos_gerais == anual_clube.objetivos_gerais

        formulario = cliente.get(f"/planeamento/anuais/{anual_equipa.id}/editar")
        assert formulario.status_code == 200
        assert "Finalização" in formulario.text

        pagina = cliente.get(f"/planeamento/anuais/{anual_equipa.id}")
        assert pagina.status_code == 200
        assert "Clube → equipa → macro → meso → micro → plano de treino" not in pagina.text
        assert "Macro → Meso → Micro → Plano de treino" in pagina.text
        assert "Objetivos do planeamento anual" in pagina.text
        assert "Calendário anual" in pagina.text

        resposta = cliente.post(f"/planeamento/equipas/{equipa.id}/macrociclos/novo", data={
            "planeamento_anual_equipa_id": str(anual_equipa.id),
            "data_inicio": "2026-07-01", "data_fim": "2026-12-31",
        }, follow_redirects=False)
        assert resposta.status_code == 303
        macro = db.query(Macrociclo).execution_options(ignorar_clube=True).filter(
            Macrociclo.planeamento_anual_equipa_id == anual_equipa.id,
        ).one()

        meso = Mesociclo(
            clube_id=clube.id, numero=1, data_inicio=date(2026, 9, 1),
            data_fim=date(2026, 9, 30), macrociclo_id=macro.id,
        )
        db.add(meso)
        db.flush()
        micro = Microciclo(
            clube_id=clube.id, numero=1, data_inicio=date(2026, 9, 7),
            data_fim=date(2026, 9, 13), mesociclo_id=meso.id,
        )
        db.add(micro)
        db.flush()
        meso_seguinte = Mesociclo(
            clube_id=clube.id, numero=2, data_inicio=date(2026, 10, 1),
            data_fim=date(2026, 10, 31), macrociclo_id=macro.id,
        )
        db.add(meso_seguinte)
        db.flush()
        micro_seguinte = Microciclo(
            clube_id=clube.id, numero=2, data_inicio=date(2026, 10, 5),
            data_fim=date(2026, 10, 11), mesociclo_id=meso_seguinte.id,
        )
        db.add(micro_seguinte)
        db.flush()
        sessao = SessaoTreino(
            clube_id=clube.id, data=date(2026, 9, 8), microciclo_id=micro.id,
            hora_inicio="18:00", hora_fim="19:30", numero_treino=2,
        )
        db.add(sessao)
        db.flush()
        sessao_anterior = SessaoTreino(
            clube_id=clube.id, data=date(2026, 9, 7), microciclo_id=micro.id,
            hora_inicio="18:00", hora_fim="19:30", numero_treino=1,
        )
        db.add(sessao_anterior)
        db.flush()
        plano = PlanoTreino(clube_id=clube.id, sessao_id=sessao.id, objectivos="Treino integrado")
        db.add(plano)
        db.commit()
        assert plano.sessao.microciclo.mesociclo.macrociclo.planeamento_anual_equipa.id == anual_equipa.id
        assert anual_equipa.planeamento_clube_anual.id == anual_clube.id

        pagina_mesos = cliente.get(f"/planeamento/equipas/{equipa.id}/mesociclos")
        assert pagina_mesos.status_code == 200
        assert 'data-cycle-list="mesociclos"' in pagina_mesos.text
        assert pagina_mesos.text.index('data-cycle-number="1"') < pagina_mesos.text.index('data-cycle-number="2"')

        pagina_micros = cliente.get(f"/planeamento/equipas/{equipa.id}/microciclos")
        assert pagina_micros.status_code == 200
        assert 'data-cycle-list="microciclos"' in pagina_micros.text
        assert pagina_micros.text.index('data-cycle-number="1"') < pagina_micros.text.index('data-cycle-number="2"')

        pagina_treinos = cliente.get(f"/treino/equipas/{equipa.id}/planos")
        assert pagina_treinos.status_code == 200
        assert "data-training-list" in pagina_treinos.text
        assert pagina_treinos.text.index('data-training-card-number="1"') < pagina_treinos.text.index('data-training-card-number="2"')

        bloqueio = cliente.get(f"/planeamento/equipas/{equipa_externa.id}/anuais", follow_redirects=False)
        assert bloqueio.status_code in (302, 303)
    finally:
        db.rollback()
        treinador.equipas.clear()
        db.commit()
        for modelo in (PlanoTreino, SessaoTreino, Microciclo, Mesociclo, Macrociclo, PlaneamentoAnualEquipa):
            db.query(modelo).execution_options(ignorar_clube=True).filter(
                modelo.clube_id == clube.id,
            ).delete(synchronize_session=False)
        db.query(Utilizador).execution_options(ignorar_clube=True).filter(Utilizador.id == utilizador.id).delete()
        db.query(Treinador).execution_options(ignorar_clube=True).filter(Treinador.id == treinador.id).delete()
        db.query(PlaneamentoClubeAnual).execution_options(ignorar_clube=True).filter(
            PlaneamentoClubeAnual.id == anual_clube.id,
        ).delete()
        db.query(Equipa).execution_options(ignorar_clube=True).filter(
            Equipa.id.in_([equipa.id, equipa_externa.id]),
        ).delete(synchronize_session=False)
        db.query(Clube).filter(Clube.id.in_([clube.id, outro_clube.id])).delete(synchronize_session=False)
        db.commit()
        db.close()

from datetime import date
from io import BytesIO
from uuid import uuid4

from pypdf import PdfReader

from auth import encriptar_password
from database import SessionLocal
from main import app
from models.clube import Clube
from models.equipa import Equipa, EscalaoEnum, GeneroEnum
from models.jogo import Jogo
from models.planeamento import (
    ConteudoMapaAnual,
    ConteudoMapaAnualOculto,
    Macrociclo,
    Mesociclo,
    Microciclo,
    PlaneamentoAnualEquipa,
    PrioridadeConteudoMapaAnual,
)
from models.treinador import Treinador
from models.utilizador import PerfilEnum, Utilizador
from services.mapa_conteudos_service import construir_mapa_conteudos, construir_semanas
from testsupport import TestClient


def test_semanas_do_mapa_cobrem_limites_e_meses_variaveis():
    semanas = construir_semanas(date(2026, 9, 1), date(2026, 10, 15))

    assert semanas[0]["inicio"] == date(2026, 8, 31)
    assert semanas[0]["fim"] == date(2026, 9, 6)
    assert semanas[-1]["inicio"] == date(2026, 10, 12)
    assert semanas[-1]["fim"] == date(2026, 10, 18)
    assert semanas[0]["mes_ano"] == (2026, 9)
    assert semanas[-1]["mes_ano"] == (2026, 10)
    assert all((semana["fim"] - semana["inicio"]).days == 6 for semana in semanas)

    epoca = construir_semanas(date(2026, 9, 1), date(2027, 6, 30))
    assert epoca[0]["mes_ano"] == (2026, 9)
    assert epoca[-1]["mes_ano"] == (2027, 6)


def test_mapa_anual_carrega_contexto_e_guarda_prioridades_com_isolamento():
    sufixo = uuid4().hex[:10]
    db = SessionLocal()
    cliente = TestClient(app)
    clube = Clube(
        nome_oficial=f"Clube mapa {sufixo}",
        nome_curto=f"CM {sufixo}",
        identificador=f"mapa-{sufixo}",
        cor_principal="#b91c1c",
        cor_secundaria="#172033",
        cor_destaque="#eab308",
    )
    db.add(clube)
    db.flush()
    equipa = Equipa(
        clube_id=clube.id,
        nome=f"Equipa mapa {sufixo}",
        escalao=EscalaoEnum.sub18,
        genero=GeneroEnum.feminino,
    )
    equipa_sem_acesso = Equipa(
        clube_id=clube.id,
        nome=f"Equipa reservada {sufixo}",
        escalao=EscalaoEnum.sub16,
        genero=GeneroEnum.feminino,
    )
    treinador = Treinador(clube_id=clube.id, nome=f"Treinador Mapa {sufixo}")
    db.add_all([equipa, equipa_sem_acesso, treinador])
    db.flush()
    treinador.equipas.append(equipa)
    password = f"Teste-{sufixo}!"
    utilizador = Utilizador(
        clube_id=clube.id,
        treinador_id=treinador.id,
        nome=f"Coach Mapa {sufixo}",
        username=f"coach-mapa-{sufixo}",
        email=f"coach-mapa-{sufixo}@example.test",
        password_hash=encriptar_password(password),
        perfil=PerfilEnum.treinador,
        ativo=True,
    )
    anual = PlaneamentoAnualEquipa(
        clube_id=clube.id,
        equipa_id=equipa.id,
        epoca="2026/2027",
        titulo="Mapa anual integrado",
        data_inicio=date(2026, 9, 1),
        data_fim=date(2027, 6, 30),
        estado="ativo",
    )
    anual_sem_acesso = PlaneamentoAnualEquipa(
        clube_id=clube.id,
        equipa_id=equipa_sem_acesso.id,
        epoca="2026/2027",
        titulo="Mapa sem acesso",
        data_inicio=date(2026, 9, 1),
        data_fim=date(2027, 6, 30),
        estado="ativo",
    )
    db.add_all([utilizador, anual, anual_sem_acesso])
    db.flush()
    macro = Macrociclo(
        clube_id=clube.id,
        equipa_id=equipa.id,
        planeamento_anual_equipa_id=anual.id,
        numero=1,
        data_inicio=date(2026, 9, 1),
        data_fim=date(2026, 12, 31),
    )
    db.add(macro)
    db.flush()
    meso = Mesociclo(
        clube_id=clube.id,
        macrociclo_id=macro.id,
        numero=1,
        data_inicio=date(2026, 9, 1),
        data_fim=date(2026, 9, 30),
    )
    db.add(meso)
    db.flush()
    micro = Microciclo(
        clube_id=clube.id,
        mesociclo_id=meso.id,
        numero=1,
        data_inicio=date(2026, 9, 7),
        data_fim=date(2026, 9, 13),
    )
    jogo = Jogo(
        clube_id=clube.id,
        equipa_id=equipa.id,
        data=date(2026, 9, 12),
        adversario="Adversario Mapa",
        competicao="Proliga",
        em_casa=False,
    )
    db.add_all([micro, jogo])
    db.commit()

    try:
        resposta = cliente.post("/login-form", data={"username": utilizador.username, "password": password}, follow_redirects=False)
        assert resposta.status_code == 303

        pagina = cliente.get(f"/planeamento/anuais/{anual.id}")
        assert pagina.status_code == 200
        assert "Mapa de conteúdos" in pagina.text
        assert "Passe + receção" in pagina.text
        assert "Adversario Mapa" in pagina.text
        assert "Proliga" in pagina.text
        assert "Macro 1" in pagina.text
        assert "Meso 1" in pagina.text
        assert "Micro 1" in pagina.text
        assert f'href="/planeamento/macrociclos/{macro.id}"' in pagina.text
        assert f'href="/planeamento/mesociclos/{meso.id}"' in pagina.text
        assert f'href="/planeamento/microciclos/{micro.id}"' in pagina.text
        assert f'href="/jogos/{jogo.id}"' in pagina.text
        assert "+ Conteúdo" in pagina.text
        assert "Exportar A3" in pagina.text

        db.expire_all()
        conteudo = db.query(ConteudoMapaAnual).execution_options(ignorar_clube=True).filter(
            ConteudoMapaAnual.clube_id == clube.id,
            ConteudoMapaAnual.codigo == "tecnica-ofensiva-passe-rececao",
        ).one()
        payload = {"alteracoes": [{
            "conteudo_id": conteudo.id,
            "semana_inicio": "2026-09-07",
            "prioridade": 1,
        }]}
        guardada = cliente.post(f"/planeamento/anuais/{anual.id}/mapa-conteudos/prioridades", json=payload)
        assert guardada.status_code == 200
        assert guardada.json()["criadas"] == 1

        db.expire_all()
        prioridade = db.query(PrioridadeConteudoMapaAnual).execution_options(ignorar_clube=True).filter(
            PrioridadeConteudoMapaAnual.planeamento_anual_id == anual.id,
        ).one()
        assert prioridade.prioridade == 1
        assert prioridade.microciclo_id == micro.id
        assert 'data-value="1"' in cliente.get(f"/planeamento/anuais/{anual.id}").text
        pagina_micro = cliente.get(f"/planeamento/microciclos/{micro.id}")
        assert pagina_micro.status_code == 200
        assert "Prioridades do mapa anual de conteúdos" in pagina_micro.text
        assert "Passe + receção" in pagina_micro.text

        # Uma alteração de datas não pode deixar uma prioridade ligada a um
        # microciclo antigo. A semana volta a ser ligada assim que coincide.
        micro.data_inicio = date(2026, 10, 5)
        micro.data_fim = date(2026, 10, 11)
        db.commit()
        construir_mapa_conteudos(db, anual)
        assert prioridade.microciclo_id is None
        micro.data_inicio = date(2026, 9, 7)
        micro.data_fim = date(2026, 9, 13)
        construir_mapa_conteudos(db, anual)
        assert prioridade.microciclo_id == micro.id
        db.commit()

        payload["alteracoes"][0]["prioridade"] = 2
        atualizada = cliente.post(f"/planeamento/anuais/{anual.id}/mapa-conteudos/prioridades", json=payload)
        assert atualizada.status_code == 200
        assert atualizada.json()["atualizadas"] == 1

        invalida = cliente.post(f"/planeamento/anuais/{anual.id}/mapa-conteudos/prioridades", json={
            "alteracoes": [{"conteudo_id": conteudo.id, "semana_inicio": "2026-09-07", "prioridade": 3}],
        })
        assert invalida.status_code == 422

        payload["alteracoes"][0]["prioridade"] = None
        removida = cliente.post(f"/planeamento/anuais/{anual.id}/mapa-conteudos/prioridades", json=payload)
        assert removida.status_code == 200
        assert removida.json()["removidas"] == 1
        assert db.query(PrioridadeConteudoMapaAnual).execution_options(ignorar_clube=True).filter(
            PrioridadeConteudoMapaAnual.planeamento_anual_id == anual.id,
        ).count() == 0

        criado = cliente.post(f"/planeamento/anuais/{anual.id}/mapa-conteudos/conteudos", json={
            "area": "Tática Ofensiva",
            "subarea": "Coletiva ofensiva",
            "nome": "Ataque contra zona",
        })
        assert criado.status_code == 200
        conteudo_personalizado_id = criado.json()["conteudo_id"]
        db.expire_all()
        conteudo_personalizado = db.query(ConteudoMapaAnual).execution_options(ignorar_clube=True).filter(
            ConteudoMapaAnual.id == conteudo_personalizado_id,
        ).one()
        assert conteudo_personalizado.planeamento_anual_id == anual.id
        assert "Ataque contra zona" in cliente.get(f"/planeamento/anuais/{anual.id}").text

        pdf = cliente.get(f"/planeamento/anuais/{anual.id}/mapa-conteudos/pdf")
        assert pdf.status_code == 200
        assert pdf.headers["content-type"].startswith("application/pdf")
        leitor = PdfReader(BytesIO(pdf.content))
        assert len(leitor.pages) == 1
        pagina_pdf = leitor.pages[0]
        assert float(pagina_pdf.mediabox.width) > float(pagina_pdf.mediabox.height)
        assert 1180 < float(pagina_pdf.mediabox.width) < 1200

        eliminada_personalizada = cliente.post(
            f"/planeamento/anuais/{anual.id}/mapa-conteudos/conteudos/{conteudo_personalizado_id}/eliminar",
            json={},
        )
        assert eliminada_personalizada.status_code == 200
        assert "Ataque contra zona" not in cliente.get(f"/planeamento/anuais/{anual.id}").text

        eliminado_catalogo = cliente.post(
            f"/planeamento/anuais/{anual.id}/mapa-conteudos/conteudos/{conteudo.id}/eliminar",
            json={},
        )
        assert eliminado_catalogo.status_code == 200
        db.expire_all()
        assert db.query(ConteudoMapaAnual).execution_options(ignorar_clube=True).filter(
            ConteudoMapaAnual.id == conteudo.id,
            ConteudoMapaAnual.ativo.is_(True),
        ).count() == 1
        assert db.query(ConteudoMapaAnualOculto).execution_options(ignorar_clube=True).filter(
            ConteudoMapaAnualOculto.planeamento_anual_id == anual.id,
            ConteudoMapaAnualOculto.conteudo_id == conteudo.id,
        ).count() == 1
        assert "Passe + receção" not in cliente.get(f"/planeamento/anuais/{anual.id}").text

        bloqueada = cliente.get(f"/planeamento/anuais/{anual_sem_acesso.id}", follow_redirects=False)
        assert bloqueada.status_code in (302, 303)
        bloqueada_criacao = cliente.post(
            f"/planeamento/anuais/{anual_sem_acesso.id}/mapa-conteudos/conteudos",
            json={"area": "Técnica Ofensiva", "nome": "Sem acesso"},
            follow_redirects=False,
        )
        assert bloqueada_criacao.status_code in (302, 303)
        bloqueada_pdf = cliente.get(
            f"/planeamento/anuais/{anual_sem_acesso.id}/mapa-conteudos/pdf",
            follow_redirects=False,
        )
        assert bloqueada_pdf.status_code in (302, 303)
    finally:
        db.rollback()
        treinador.equipas.clear()
        db.commit()
        for modelo in (
            PrioridadeConteudoMapaAnual,
            ConteudoMapaAnualOculto,
            ConteudoMapaAnual,
            Jogo,
            Microciclo,
            Mesociclo,
            Macrociclo,
            PlaneamentoAnualEquipa,
        ):
            db.query(modelo).execution_options(ignorar_clube=True).filter(
                modelo.clube_id == clube.id,
            ).delete(synchronize_session=False)
        db.query(Utilizador).execution_options(ignorar_clube=True).filter(Utilizador.id == utilizador.id).delete()
        db.query(Treinador).execution_options(ignorar_clube=True).filter(Treinador.id == treinador.id).delete()
        db.query(Equipa).execution_options(ignorar_clube=True).filter(
            Equipa.id.in_([equipa.id, equipa_sem_acesso.id]),
        ).delete(synchronize_session=False)
        db.query(Clube).filter(Clube.id == clube.id).delete()
        db.commit()
        db.close()

from pathlib import Path

import pytest

from database import SessionLocal
from models.equipa import Equipa
from models.playbook import (
    CadernoPlaybook,
    JogadaCadernoPlaybook,
    Playbook,
    SecaoCadernoPlaybook,
    SetPlay,
)
from models.utilizador import Utilizador


ROOT = Path(__file__).resolve().parents[2]


def test_caderno_reutiliza_jogadas_e_guarda_ordenacao_sem_refresh(client_admin):
    db = SessionLocal()
    caderno_id = None
    jogadas_criadas = []
    try:
        administrador = db.query(Utilizador).filter(Utilizador.username == "admin").first()
        if not administrador or not administrador.clube_id:
            pytest.skip("Conta administrativa de teste sem clube.")
        equipa = db.query(Equipa).filter(Equipa.clube_id == administrador.clube_id).first()
        if not equipa:
            pytest.skip("Clube de teste sem equipa.")
        biblioteca = db.query(Playbook).filter(Playbook.equipa_id == equipa.id).first()
        if not biblioteca:
            biblioteca = Playbook(
                clube_id=administrador.clube_id,
                equipa_id=equipa.id,
                nome=f"Playbook — {equipa.nome}",
            )
            db.add(biblioteca)
            db.commit()
            db.refresh(biblioteca)

        for indice in range(2):
            jogada = SetPlay(
                clube_id=administrador.clube_id,
                playbook_id=biblioteca.id,
                nome=f"Jogada teste caderno {indice}",
                categoria="Ataque",
                ordem=900 + indice,
            )
            db.add(jogada)
            db.flush()
            jogadas_criadas.append(jogada.id)
        db.commit()

        resposta = client_admin.post(
            f"/playbook/equipas/{equipa.id}/cadernos/novo",
            data={"nome": "Caderno teste", "descricao": "Organização de teste"},
            follow_redirects=False,
        )
        assert resposta.status_code == 303
        db.expire_all()
        caderno = db.query(CadernoPlaybook).filter(CadernoPlaybook.nome == "Caderno teste").order_by(CadernoPlaybook.id.desc()).first()
        assert caderno is not None
        caderno_id = caderno.id

        resposta = client_admin.post(
            f"/playbook/cadernos/{caderno.id}/secoes/novo",
            data={"nome": "Transição"},
            follow_redirects=False,
        )
        assert resposta.status_code == 303
        db.expire_all()
        secao = db.query(SecaoCadernoPlaybook).filter(SecaoCadernoPlaybook.caderno_id == caderno.id).first()
        assert secao is not None

        resposta = client_admin.post(
            f"/playbook/cadernos/{caderno.id}/jogadas/adicionar",
            data={"setplay_ids": [str(jogada_id) for jogada_id in jogadas_criadas], "secao_id": str(secao.id)},
            follow_redirects=False,
        )
        assert resposta.status_code == 303
        db.expire_all()
        entradas = db.query(JogadaCadernoPlaybook).filter(JogadaCadernoPlaybook.caderno_id == caderno.id).order_by(JogadaCadernoPlaybook.id).all()
        assert len(entradas) == 2

        resposta = client_admin.post(
            f"/playbook/cadernos/{caderno.id}/reordenar",
            json={"grupos": [
                {"secao_id": None, "jogada_ids": [entradas[1].id]},
                {"secao_id": secao.id, "jogada_ids": [entradas[0].id]},
            ]},
        )
        assert resposta.status_code == 200
        assert resposta.json() == {"sucesso": True}
        db.expire_all()
        assert db.get(JogadaCadernoPlaybook, entradas[1].id).secao_id is None
        assert db.get(JogadaCadernoPlaybook, entradas[0].id).secao_id == secao.id

        detalhe = client_admin.get(f"/playbook/cadernos/{caderno.id}")
        assert detalhe.status_code == 200
        assert "Arrasta os cartões" in detalhe.text
        assert "data-book-dropzone" in detalhe.text
        assert all(nome in detalhe.text for nome in ("Jogada teste caderno 0", "Jogada teste caderno 1"))

        pdf = client_admin.get(f"/playbook/cadernos/{caderno.id}/pdf")
        assert pdf.status_code == 200
        assert pdf.headers["content-type"] == "application/pdf"
        assert pdf.content.startswith(b"%PDF")
    finally:
        if caderno_id:
            caderno = db.get(CadernoPlaybook, caderno_id)
            if caderno:
                db.delete(caderno)
                db.commit()
        if jogadas_criadas:
            db.query(SetPlay).filter(SetPlay.id.in_(jogadas_criadas)).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_interface_playbook_tem_biblioteca_cadernos_e_editor_unificado():
    lista = (ROOT / "frontend/templates/playbook/lista.html").read_text(encoding="utf-8")
    caderno = (ROOT / "frontend/templates/playbook/caderno.html").read_text(encoding="utf-8")
    caderno_pdf = (ROOT / "frontend/templates/playbook/caderno_pdf.html").read_text(encoding="utf-8")
    detalhe = (ROOT / "frontend/templates/playbook/detalhe.html").read_text(encoding="utf-8")

    assert 'data-pb-tab="biblioteca"' in lista
    assert 'data-pb-tab="cadernos"' in lista
    assert "data-book-entry" in caderno
    assert "data-book-dropzone" in caderno
    assert "reordenar" in caderno
    assert "/pdf" in caderno
    assert "grupo.jogadas" in caderno_pdf
    assert "data-playbook-studio" in detalhe
    assert "data-scenes-list" in detalhe
    assert "data-preview-canvas" in detalhe
    assert "Todos os movimentos desta cena acontecem ao mesmo tempo" in detalhe

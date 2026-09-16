import base64
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from PIL import Image

from models.playbook import PassoSetPlay
from models.equipa import Equipa
from models.playbook import Playbook, SetPlay
from models.utilizador import Utilizador
from database import SessionLocal
from services.imagem_playbook_service import preparar_imagem_passo


ROOT = Path(__file__).resolve().parents[2]


def _imagem_png(largura=2400, altura=1600) -> bytes:
    imagem = Image.new("RGB", (largura, altura), "#f4f4f5")
    saida = BytesIO()
    imagem.save(saida, format="PNG")
    return saida.getvalue()


def test_imagem_do_passo_e_validada_otimizada_e_codificada():
    resultado = preparar_imagem_passo(_imagem_png())

    assert resultado.startswith("data:image/jpeg;base64,")
    dados = base64.b64decode(resultado.split(",", 1)[1])
    with Image.open(BytesIO(dados)) as imagem:
        assert imagem.width <= 1800
        assert imagem.height <= 1400


def test_imagem_do_passo_rejeita_conteudo_invalido():
    with pytest.raises(ValueError, match="PNG ou JPEG válida"):
        preparar_imagem_passo(b"nao-e-uma-imagem")


def test_playbook_expoe_imagem_e_desenho_em_cada_passo():
    template = (ROOT / "frontend/templates/playbook/detalhe.html").read_text(encoding="utf-8")
    pdf = (ROOT / "frontend/templates/playbook/pdf.html").read_text(encoding="utf-8")

    assert hasattr(PassoSetPlay, "imagem_coach")
    assert hasattr(SetPlay, "origem")
    assert "Playbook Studio" in template
    assert 'data-playbook-studio' in template
    assert 'playbook-studio.js' in template
    assert 'name="imagem"' in template
    assert "/imagem/eliminar" in template
    assert "passo.imagem_composta_pdf" in pdf


def test_nova_jogada_abre_studio_com_primeira_cena_persistida(client_admin):
    db = SessionLocal()
    setplay_id = None
    try:
        administrador = db.query(Utilizador).filter(Utilizador.username == "admin").first()
        if not administrador or not administrador.clube_id:
            pytest.skip("Conta administrativa de teste sem clube.")
        equipa = db.query(Equipa).filter(Equipa.clube_id == administrador.clube_id).first()
        if not equipa:
            pytest.skip("Clube de teste sem equipa.")

        client_admin.get(f"/playbook/equipas/{equipa.id}")
        nome = f"Jogada persistida {uuid4().hex[:8]}"
        criacao = client_admin.post(
            f"/playbook/equipas/{equipa.id}/setplays/novo",
            data={"nome": nome, "categoria": "Ataque", "descricao": ""},
            follow_redirects=False,
        )
        assert criacao.status_code == 303
        setplay_id = int(criacao.headers["location"].rsplit("/", 1)[-1])

        db.expire_all()
        setplay = db.query(SetPlay).filter(SetPlay.id == setplay_id).one()
        assert setplay.clube_id == administrador.clube_id
        assert len(setplay.passos) == 1
        assert setplay.passos[0].clube_id == administrador.clube_id

        studio = client_admin.get(criacao.headers["location"])
        assert studio.status_code == 200
        assert nome in studio.text
    finally:
        if setplay_id:
            setplay = db.query(SetPlay).filter(SetPlay.id == setplay_id).first()
            if setplay:
                db.delete(setplay)
                db.commit()
        db.close()


def test_editor_tatico_comum_e_animacao_por_passos_estao_disponiveis():
    toolbar = (ROOT / "frontend/templates/partials/tactical_toolbar.html").read_text(encoding="utf-8")
    playbook = (ROOT / "frontend/templates/playbook/detalhe.html").read_text(encoding="utf-8")
    treino = (ROOT / "frontend/templates/treino/plano.html").read_text(encoding="utf-8")
    studio = (ROOT / "frontend/static/js/playbook-studio.js").read_text(encoding="utf-8")
    compatibilidade = (ROOT / "frontend/static/js/tactical-legacy.js").read_text(encoding="utf-8")

    for grupo in ("Jogadores", "Equipamento", "Movimentos", "Estilo da linha", "Edição"):
        assert grupo in toolbar
    for ferramenta in ("jogador_ataque", "jogador_defesa", "coach", "cone", "bola"):
        assert f'data-ferramenta="{ferramenta}"' in toolbar
    assert 'data-ferramenta="caneta"' in toolbar
    assert "Caneta livre" in toolbar
    assert "('seta_curva','⌒','Curva')" in toolbar
    assert "tactical_toolbar" in treino
    assert "data-playbook-studio" in playbook
    assert 'data-tool="jogador_ataque"' in playbook
    assert "data-preview-canvas" in playbook
    assert "renderPreview" in studio
    assert "actionPlan" in studio
    assert "data-group-selected" in playbook
    assert "data-numero-jogador" in toolbar
    assert ">X</span><small>Defesa" not in toolbar
    assert "estadoDesenhoParaGuardar" in treino
    assert "stateFor" in studio
    assert "sincronizarNumeroJogador" in treino
    assert "playerNumber" in studio
    assert "tactical-legacy.js" in treino
    assert "tactical-legacy.js" in playbook
    assert 'TIPO_RECORTE = "recorte_legado"' in compatibilidade
    assert "decomporImagem" in compatibilidade
    assert "contemPonto" in compatibilidade
    assert "converterImagemLegada(canvasId, imagemGuardada)" in treino
    assert "TacticalLegacy.contemPonto" in treino
    assert "TacticalLegacy.contemPonto" in studio
    assert "await window.TacticalLegacy.aguardarRecortes" in treino
    assert "await window.TacticalLegacy?.aguardarRecortes" in studio


def test_editor_tatico_suporta_apple_pencil_e_borracha_continua():
    treino = (ROOT / "frontend/templates/treino/plano.html").read_text(encoding="utf-8")
    playbook = (ROOT / "frontend/templates/playbook/detalhe.html").read_text(encoding="utf-8")
    biblioteca = (ROOT / "frontend/templates/biblioteca/detalhe.html").read_text(encoding="utf-8")
    studio = (ROOT / "frontend/static/js/playbook-studio.js").read_text(encoding="utf-8")

    for template in (treino, biblioteca):
        assert "pointerdown" in template
        assert "setPointerCapture" in template
        assert "pointercancel" in template
        assert "pointerType === 'pen'" in template
        assert "tentarAlternarFerramentaApplePencil" in template
        assert "registarFimGestoApplePencil" in template
        assert "function apagarNaPosicao" in template
        assert "function recortarTracoLivre" in template
        assert "getCoalescedEvents" in template
        assert "objecto.tipo === 'caneta'" in template
        assert "est.ferramenta === 'caneta'" in template
        assert "linha.tipo === 'caneta'" in template
        assert "finalizarLinhaPendente(canvasId)" in template

    assert 'addEventListener("pointerdown"' in studio
    assert "setPointerCapture" in studio
    assert 'addEventListener("pointercancel"' in studio
    assert 'event.pointerType === "pen"' in studio
    assert "pencilTap" in studio
    assert "function eraseAt" in studio
    assert 'object.tipo === "caneta"' in studio
    assert 'tool === "caneta"' in studio
    assert 'data-tool="caneta"' in playbook
    assert 'data-tool="borracha"' in playbook

    toolbar = (ROOT / "frontend/templates/partials/tactical_toolbar.html").read_text(encoding="utf-8")
    assert "Borracha: apagar apenas a zona percorrida" in toolbar
    assert "<small>Borracha</small>" in toolbar


def test_administrador_adiciona_e_remove_imagem_do_passo(client_admin):
    db = SessionLocal()
    playbook_id = None
    try:
        administrador = db.query(Utilizador).filter(Utilizador.username == "admin").first()
        if not administrador or not administrador.clube_id:
            pytest.skip("Conta administrativa de teste sem clube.")
        equipa = db.query(Equipa).filter(Equipa.clube_id == administrador.clube_id).first()
        if not equipa:
            pytest.skip("Clube de teste sem equipa.")

        playbook = Playbook(
            clube_id=administrador.clube_id,
            equipa_id=equipa.id,
            nome="Playbook temporário de imagem",
        )
        db.add(playbook)
        db.flush()
        playbook_id = playbook.id
        setplay = SetPlay(
            clube_id=administrador.clube_id,
            playbook_id=playbook.id,
            nome="Jogada temporária",
        )
        db.add(setplay)
        db.flush()
        passo = PassoSetPlay(
            clube_id=administrador.clube_id,
            setplay_id=setplay.id,
            ordem=0,
        )
        db.add(passo)
        db.commit()
        passo_id = passo.id

        resposta = client_admin.post(
            f"/playbook/passos/{passo_id}/imagem",
            files={"imagem": ("quadro.png", _imagem_png(800, 600), "image/png")},
            follow_redirects=False,
        )
        assert resposta.status_code == 303
        db.expire_all()
        assert db.query(PassoSetPlay).filter(PassoSetPlay.id == passo_id).one().imagem_coach

        resposta = client_admin.post(
            f"/playbook/passos/{passo_id}/imagem/eliminar",
            follow_redirects=False,
        )
        assert resposta.status_code == 303
        db.expire_all()
        assert db.query(PassoSetPlay).filter(PassoSetPlay.id == passo_id).one().imagem_coach is None
    finally:
        if playbook_id:
            playbook = db.query(Playbook).filter(Playbook.id == playbook_id).first()
            if playbook:
                db.delete(playbook)
                db.commit()
        db.close()


def test_studio_gera_e_reordena_cenas_sem_recarregar(client_admin):
    db = SessionLocal()
    playbook_id = None
    try:
        administrador = db.query(Utilizador).filter(Utilizador.username == "admin").first()
        if not administrador or not administrador.clube_id:
            pytest.skip("Conta administrativa de teste sem clube.")
        equipa = db.query(Equipa).filter(Equipa.clube_id == administrador.clube_id).first()
        if not equipa:
            pytest.skip("Clube de teste sem equipa.")

        playbook = Playbook(clube_id=administrador.clube_id, equipa_id=equipa.id, nome="Playbook Studio teste")
        db.add(playbook)
        db.flush()
        playbook_id = playbook.id
        setplay = SetPlay(clube_id=administrador.clube_id, playbook_id=playbook.id, nome="Jogada Studio")
        db.add(setplay)
        db.flush()
        primeiro = PassoSetPlay(clube_id=administrador.clube_id, setplay_id=setplay.id, ordem=0)
        db.add(primeiro)
        db.commit()

        legado = client_admin.get(f"/playbook/setplays/{setplay.id}", follow_redirects=False)
        assert legado.status_code == 303
        assert legado.headers["location"] == f"/playbook/studio/setplays/{setplay.id}"

        detalhe = client_admin.get(f"/playbook/studio/setplays/{setplay.id}")
        assert detalhe.status_code == 200
        assert "Playbook Studio" in detalhe.text
        assert 'data-scenes-list' in detalhe.text
        assert "/static/campos/campo_meio.png" in detalhe.text
        assert 'data-court-type="meio"' in detalhe.text
        assert 'data-court-type="completo"' in detalhe.text

        novo = client_admin.post(
            f"/playbook/setplays/{setplay.id}/passos/novo",
            json={},
            headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
        )
        assert novo.status_code == 200
        segundo_id = novo.json()["passo"]["id"]

        nota = client_admin.post(f"/playbook/passos/{segundo_id}/observacao-json", json={"observacao": "Corte e passe"})
        assert nota.json() == {"sucesso": True, "observacao": "Corte e passe"}

        duplicado = client_admin.post(
            f"/playbook/passos/{segundo_id}/duplicar",
            json={},
            headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
        )
        assert duplicado.status_code == 200
        terceiro_id = duplicado.json()["passo"]["id"]

        ordem = [terceiro_id, primeiro.id, segundo_id]
        resposta = client_admin.post(f"/playbook/setplays/{setplay.id}/passos/reordenar", json={"passo_ids": ordem})
        assert resposta.json() == {"sucesso": True}
        db.expire_all()
        guardados = db.query(PassoSetPlay).filter(PassoSetPlay.setplay_id == setplay.id).order_by(PassoSetPlay.ordem).all()
        assert [passo.id for passo in guardados] == ordem
    finally:
        if playbook_id:
            playbook = db.query(Playbook).filter(Playbook.id == playbook_id).first()
            if playbook:
                db.delete(playbook)
                db.commit()
        db.close()

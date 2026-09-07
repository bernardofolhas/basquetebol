import base64
from io import BytesIO
from pathlib import Path

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
    assert "Desenho tático" in template
    assert 'name="imagem"' in template
    assert "/imagem/eliminar" in template
    assert "passo.imagem_composta_pdf" in pdf


def test_editor_tatico_comum_e_animacao_por_passos_estao_disponiveis():
    toolbar = (ROOT / "frontend/templates/partials/tactical_toolbar.html").read_text(encoding="utf-8")
    playbook = (ROOT / "frontend/templates/playbook/detalhe.html").read_text(encoding="utf-8")
    treino = (ROOT / "frontend/templates/treino/plano.html").read_text(encoding="utf-8")
    compatibilidade = (ROOT / "frontend/static/js/tactical-legacy.js").read_text(encoding="utf-8")

    for grupo in ("Jogadores", "Equipamento", "Movimentos", "Estilo da linha", "Edição"):
        assert grupo in toolbar
    for ferramenta in ("jogador_ataque", "jogador_defesa", "coach", "cone", "bola"):
        assert f'data-ferramenta="{ferramenta}"' in toolbar
    assert 'data-ferramenta="caneta"' in toolbar
    assert "Caneta livre" in toolbar
    assert "('seta_curva','⌒','Curva')" in toolbar
    assert "tactical_toolbar" in treino
    assert "tactical_toolbar" in playbook
    assert "data-playbook-player" in playbook
    assert "inicializarAnimacaoPlaybook" in playbook
    assert "data-player-play" in playbook
    assert "data-numero-jogador" in toolbar
    assert ">X</span><small>Defesa" not in toolbar
    assert "estadoDesenhoParaGuardar" in treino
    assert "estadoDesenhoParaGuardar" in playbook
    assert "sincronizarNumeroJogador" in treino
    assert "sincronizarNumeroJogador" in playbook
    assert "tactical-legacy.js" in treino
    assert "tactical-legacy.js" in playbook
    assert 'TIPO_RECORTE = "recorte_legado"' in compatibilidade
    assert "decomporImagem" in compatibilidade
    assert "contemPonto" in compatibilidade
    assert "converterImagemLegada(canvasId, imagemGuardada)" in treino
    assert "TacticalLegacy.contemPonto" in treino
    assert "TacticalLegacy.contemPonto" in playbook
    assert "await window.TacticalLegacy.aguardarRecortes" in treino
    assert "await window.TacticalLegacy.aguardarRecortes" in playbook


def test_editor_tatico_suporta_apple_pencil_e_borracha_continua():
    treino = (ROOT / "frontend/templates/treino/plano.html").read_text(encoding="utf-8")
    playbook = (ROOT / "frontend/templates/playbook/detalhe.html").read_text(encoding="utf-8")
    biblioteca = (ROOT / "frontend/templates/biblioteca/detalhe.html").read_text(encoding="utf-8")

    for template in (treino, playbook, biblioteca):
        assert "pointerdown" in template
        assert "setPointerCapture" in template
        assert "pointercancel" in template
        assert "pointerType === 'pen'" in template
        assert "function apagarNaPosicao" in template
        assert "est.ferramenta === 'caneta'" in template
        assert "linha.tipo === 'caneta'" in template
        assert "finalizarLinhaPendente(canvasId)" in template


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

import base64
import io
import zipfile
from pathlib import Path

import pytest
from PIL import Image

from database import SessionLocal
from models.equipa import Equipa
from models.playbook import PassoSetPlay, Playbook, SetPlay
from models.utilizador import Utilizador
from services.importacao_ebp_service import _ponto, interpretar_ebp, renderizar_sequencia_ebp


ROOT = Path(__file__).resolve().parents[2]


def _grafico(numero: int, tipo: str, x1: int, y1: int, x2: int = 0, y2: int = 100) -> str:
    return "\n".join((
        f"Graphicnr= {numero}",
        f"type     = {tipo}",
        f"x1       = {x1}",
        f"y1       = {y1}",
        f"x2       = {x2}",
        f"y2       = {y2}",
        "color    = 16737894",
        "playtext = ",
    ))


def _ficheiro_ebp() -> bytes:
    texto = "\n".join((
        "Version  = Basketball Playbook 0.9",
        "Type     = Play",
        "Category = Testes",
        "Playname = Wave + Flare",
        "Nr_seq   = 2",
        "Text     = Primeiro movimento",
        "Nr_parts = 3",
        _grafico(4, "Court", 0, 0),
        _grafico(1, "circle", 1600, 2800),
        _grafico(0, "ppass", 1600, 2800, 4300, 1800),
        "Animation= No",
        "Text     = Segundo movimento",
        "Focus    = ",
        "Nr_parts = 2",
        _grafico(4, "Court", 0, 0),
        _grafico(2, "circle", 4300, 1800),
    )).encode("cp1252")
    arquivo = io.BytesIO()
    with zipfile.ZipFile(arquivo, "w", compression=zipfile.ZIP_DEFLATED) as zip_ebp:
        zip_ebp.writestr("Playbook.ebp", texto)
    conteudo = arquivo.getvalue()
    return b"EBP" + conteudo[3:]


def test_interpreta_e_renderiza_cada_sequencia_do_ebp():
    jogada = interpretar_ebp(_ficheiro_ebp())

    assert jogada.nome == "Wave + Flare"
    assert jogada.categoria_origem == "Testes"
    assert len(jogada.sequencias) == 2
    assert jogada.sequencias[0].texto == "Primeiro movimento"
    assert jogada.sequencias[1].texto == "Segundo movimento"
    imagem = renderizar_sequencia_ebp(jogada.sequencias[0])
    assert imagem.startswith("data:image/png;base64,")
    with Image.open(io.BytesIO(base64.b64decode(imagem.split(",", 1)[1]))) as desenho:
        assert desenho.size == (1400, 1225)


def test_converte_coordenadas_para_a_area_util_real_do_campo_ebp():
    # Coordenadas reais do Flex 5: antes da correcao, o jogador 1 era cortado
    # no fundo e os jogadores 2/3 surgiam demasiado abaixo no campo.
    assert _ponto(816, 1970) == (95, 103)
    assert _ponto(3484, 5894) == (660, 926)
    assert _ponto(6644, 1970) == (1328, 103)


@pytest.mark.parametrize("conteudo", (b"", b"nao-e-ebp", b"EBP\x04invalido"))
def test_rejeita_ficheiros_ebp_invalidos(conteudo):
    with pytest.raises(ValueError):
        interpretar_ebp(conteudo)


def test_administrador_importa_ebp_com_imagem_independente_por_passo(client_admin):
    db = SessionLocal()
    setplay_id = None
    try:
        administrador = db.query(Utilizador).filter(Utilizador.username == "admin").first()
        if not administrador or not administrador.clube_id:
            pytest.skip("Conta administrativa de teste sem clube.")
        equipa = db.query(Equipa).filter(Equipa.clube_id == administrador.clube_id).first()
        if not equipa:
            pytest.skip("Clube de teste sem equipa.")

        resposta = client_admin.post(
            f"/playbook/equipas/{equipa.id}/setplays/importar-ebp",
            data={"categoria": "Ataque"},
            files={"ficheiro": ("wave-flare.ebp", _ficheiro_ebp(), "application/octet-stream")},
            follow_redirects=False,
        )

        assert resposta.status_code == 303
        db.expire_all()
        setplay = (
            db.query(SetPlay)
            .join(Playbook)
            .filter(Playbook.equipa_id == equipa.id, SetPlay.nome == "Wave + Flare")
            .order_by(SetPlay.id.desc())
            .first()
        )
        assert setplay is not None
        setplay_id = setplay.id
        assert setplay.categoria == "Ataque"
        assert setplay.origem == "ebp"
        passos = db.query(PassoSetPlay).filter(PassoSetPlay.setplay_id == setplay.id).order_by(PassoSetPlay.ordem).all()
        assert len(passos) == 2
        assert all(passo.imagem_coach for passo in passos)
        assert [passo.observacao for passo in passos] == ["Primeiro movimento", "Segundo movimento"]
        assert resposta.headers["location"] == f"/playbook/studio/setplays/{setplay.id}"

        detalhe = client_admin.get(f"/playbook/setplays/{setplay.id}")
        assert detalhe.status_code == 200
        assert "Imagem original do passo importado." in detalhe.text
        assert "Desenho tático" not in detalhe.text
        assert f'id="canvas_{passos[0].id}"' not in detalhe.text

        repetida = client_admin.post(
            f"/playbook/equipas/{equipa.id}/setplays/importar-ebp",
            data={"categoria": "Ataque"},
            files={"ficheiro": ("wave-flare.ebp", _ficheiro_ebp(), "application/octet-stream")},
            follow_redirects=False,
        )
        assert repetida.status_code == 303
        assert repetida.headers["location"] == f"/playbook/studio/setplays/{setplay.id}"
        total = (
            db.query(SetPlay)
            .join(Playbook)
            .filter(Playbook.equipa_id == equipa.id, SetPlay.nome == "Wave + Flare")
            .count()
        )
        assert total == 1
    finally:
        if setplay_id:
            setplay = db.query(SetPlay).filter(SetPlay.id == setplay_id).first()
            if setplay:
                db.delete(setplay)
                db.commit()
        db.close()


def test_interface_mantem_desenho_manual_e_isola_importacoes_ebp():
    lista = (ROOT / "frontend/templates/playbook/lista.html").read_text(encoding="utf-8")
    detalhe = (ROOT / "frontend/templates/playbook/detalhe.html").read_text(encoding="utf-8")

    assert "Importar ficheiro EBP" in lista
    assert 'accept=".ebp,application/octet-stream"' in lista
    assert "setplay.origem == 'ebp'" in detalhe
    assert "Imagem original do passo importado." in detalhe
    assert "data-playbook-studio" in detalhe
    assert "playbook-studio.js" in detalhe
    assert 'name="imagem"' in detalhe
    assert "/imagem/eliminar" in detalhe

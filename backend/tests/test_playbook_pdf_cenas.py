from io import BytesIO
from types import SimpleNamespace as Item

from pypdf import PdfReader
from starlette.requests import Request

from paths import STATIC_DIR
from routers import playbook
from routers.exportacoes import _passos_setplay_pdf, _playbook_coletivo
from services.desenho_service import (
    empacotar_desenho_editavel,
    imagem_estatica_data_uri,
    passo_tem_desenho_pdf,
)
from services.plano_jogo_service import graficos_plano
from services.pdf_service import renderizar_pdf


def _cenas():
    imagem = imagem_estatica_data_uri(STATIC_DIR / "campos" / "campo_meio.png")

    def passo(ordem, objectos, observacao):
        desenho = empacotar_desenho_editavel(imagem, {"campoTipo": "meio", "objectos": objectos})
        return Item(ordem=ordem, desenho=desenho, imagem_coach=None, observacao=observacao)

    return [
        passo(0, [{"tipo": "jogador_ataque", "x": 100, "y": 100}], "Posição inicial"),
        passo(1, [{"tipo": "jogador_ataque", "x": 180, "y": 100},
                   {"tipo": "seta_curva", "pontos": [{"x": 100, "y": 100}, {"x": 180, "y": 100}]}], "Movimento"),
        passo(2, [{"tipo": "bola", "x": 250, "y": 200}], "Transição"),
        passo(3, [{"tipo": "caneta", "pontos": [{"x": 200, "y": 200}, {"x": 250, "y": 230}]}], "Desenho final"),
    ]


def test_apenas_cenas_com_tracos_ou_imagem_propria_entram_no_pdf():
    passos = _cenas()
    imagem = imagem_estatica_data_uri(STATIC_DIR / "campos" / "campo_meio.png")
    assert [passo_tem_desenho_pdf(passo) for passo in passos] == [False, True, False, True]
    assert passo_tem_desenho_pdf(Item(desenho=None, imagem_coach=imagem))
    assert passo_tem_desenho_pdf(Item(desenho=imagem, imagem_coach=None))  # PNG legado
    assert not passo_tem_desenho_pdf(Item(desenho=None, imagem_coach=None, observacao="Só nota"))
    assert not passo_tem_desenho_pdf(Item(desenho=empacotar_desenho_editavel(
        imagem, {"objectos": []}), imagem_coach=None))
    assert not passo_tem_desenho_pdf(Item(desenho=empacotar_desenho_editavel(
        imagem, {"objectos": [{"tipo": "seta", "hidden": True}]}), imagem_coach=None))


def test_relatorios_exportam_so_cenas_desenhadas_sem_renumerar():
    setplay = Item(id=7, nome="Horns", descricao=None, passos=_cenas())
    pdf = _passos_setplay_pdf(setplay)
    assert [passo["ordem"] for passo in pdf] == [2, 4]
    assert [passo["observacao"] for passo in pdf] == ["Movimento", "Desenho final"]

    adversario = Item(momentos_playbook=[Item(setplay=setplay)])
    jogadas = _playbook_coletivo(adversario, {7: pdf})
    assert [passo["passo"] for passo in jogadas[0]["passos"]] == [2, 4]
    assert _playbook_coletivo(adversario, {7: []}) == []

    plano = Item(jogadas=[Item(id=9, setplay=setplay)])
    assert [grafico["passo"] for grafico in graficos_plano(plano)] == [2, 4]


def test_pdf_da_jogada_nao_mostra_cenas_de_transicao(monkeypatch):
    setplay = Item(nome="Horns", passos=_cenas(), playbook=Item(equipa=Item(nome="Rivais")))
    contexto = {}
    monkeypatch.setattr(playbook, "_equipa_id_por_setplay", lambda *_: 1)
    monkeypatch.setattr(playbook, "_verificar_acesso_playbook", lambda *_: None)
    monkeypatch.setattr(playbook, "renderizar_pdf", lambda _request, _template, dados: contexto.update(dados) or b"pdf")
    db = Item(query=lambda _modelo: Item(filter=lambda *_: Item(first=lambda: setplay)))
    pedido = Request({"type": "http", "method": "GET", "path": "/", "query_string": b"", "headers": []})

    resposta = playbook.exportar_pdf_setplay(7, pedido, db=db, utilizador=object())

    assert resposta.status_code == 200
    assert [passo.ordem for passo in contexto["passos"]] == [1, 3]
    assert all(passo.imagem_composta_pdf for passo in contexto["passos"])
    pdf = renderizar_pdf(pedido, "playbook/pdf.html", contexto)
    texto = " ".join(pagina.extract_text() for pagina in PdfReader(BytesIO(pdf)).pages)
    assert "CENA 2" in texto.upper() and "CENA 4" in texto.upper()
    assert "Posição inicial" not in texto and "Transição" not in texto


def test_pdf_do_caderno_omite_jogadas_sem_cenas_desenhadas(monkeypatch):
    desenhado = Item(nome="Horns", categoria="Ataque", descricao=None, passos=_cenas())
    transicao = Item(nome="Transição", categoria="Ataque", descricao=None, passos=_cenas()[:1])
    entradas = [Item(id=1, secao_id=None, setplay=desenhado),
                Item(id=2, secao_id=None, setplay=transicao)]
    caderno = Item(nome="Caderno", descricao=None, jogadas=entradas, secoes=[], equipa=Item(nome="Rivais"))
    contexto = {}
    monkeypatch.setattr(playbook, "_equipa_id_por_caderno", lambda *_: 1)
    monkeypatch.setattr(playbook, "_verificar_acesso_playbook", lambda *_: None)
    monkeypatch.setattr(playbook, "renderizar_pdf", lambda _request, _template, dados: contexto.update(dados) or b"pdf")
    db = Item(query=lambda _modelo: Item(filter=lambda *_: Item(first=lambda: caderno)))
    pedido = Request({"type": "http", "method": "GET", "path": "/", "query_string": b"", "headers": []})

    resposta = playbook.exportar_pdf_caderno(3, pedido, db=db, utilizador=object())

    assert resposta.status_code == 200
    assert contexto["total_jogadas_pdf"] == 1
    assert [entrada.id for entrada in contexto["grupos"][0]["jogadas"]] == [1]
    assert [passo.ordem for passo in contexto["passos_por_jogada"][1]] == [1, 3]
    assert contexto["passos_por_jogada"][2] == []
    pdf = renderizar_pdf(pedido, "playbook/caderno_pdf.html", contexto)
    texto = " ".join(pagina.extract_text() for pagina in PdfReader(BytesIO(pdf)).pages)
    assert "Horns" in texto and "Transição" not in texto
    assert "CENA 2" in texto.upper() and "CENA 4" in texto.upper()

import base64
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from services.plano_jogo_service import (
    conteudo_plano_por_categoria,
    jogo_em_preparacao,
    jogos_em_preparacao,
    preview_jogada,
)


ROOT = Path(__file__).resolve().parents[2]


def test_conteudo_do_relatorio_prioriza_escolhas_e_recupera_planos_antigos():
    plano = SimpleNamespace(
        itens=[SimpleNamespace(item=SimpleNamespace(categoria="chave_ataque", texto="  Atacar cedo  "))],
        chaves_ataque="Texto antigo",
        bloqueio_direto_lateral="Forçar para a linha\nTrocar no segundo bloqueio",
    )

    conteudo = conteudo_plano_por_categoria(plano)

    assert conteudo["chave_ataque"] == ["Atacar cedo"]
    assert conteudo["bloqueio_direto_lateral"] == ["Forçar para a linha", "Trocar no segundo bloqueio"]
    assert conteudo["bloqueio_direto_central"] == []
    assert not any(conteudo_plano_por_categoria(None).values())


def test_jogos_em_preparacao_excluem_passados_e_escolhem_o_mais_proximo():
    hoje = date(2026, 9, 29)
    jogos = [
        SimpleNamespace(id=1, data=hoje - timedelta(days=1), hora="21:00"),
        SimpleNamespace(id=4, data=hoje + timedelta(days=10), hora="18:00"),
        SimpleNamespace(id=3, data=hoje + timedelta(days=2), hora="20:00"),
        SimpleNamespace(id=2, data=hoje, hora="22:00"),
    ]

    ordenados = jogos_em_preparacao(jogos, hoje)

    assert [jogo.id for jogo in ordenados] == [2, 3, 4]
    assert jogo_em_preparacao(jogos[0], hoje) is False
    assert jogo_em_preparacao(jogos[-1], hoje) is True


def test_scouting_e_exportacao_bloqueiam_planos_de_jogos_passados():
    scouting = (ROOT / "backend" / "routers" / "scouting.py").read_text(encoding="utf-8")
    jogos = (ROOT / "backend" / "routers" / "jogos.py").read_text(encoding="utf-8")
    exportacoes = (ROOT / "backend" / "routers" / "exportacoes.py").read_text(encoding="utf-8")
    relatorios = (ROOT / "frontend" / "templates" / "scouting" / "relatorios.html").read_text(encoding="utf-8")

    assert "jogos_futuros = jogos_em_preparacao(jogos)" in scouting
    assert "not jogo_em_preparacao(relatorio.jogo)" in scouting
    assert "not jogo_em_preparacao(jogo)" in jogos
    assert "Nao e possivel exportar um plano de jogo ja realizado" in exportacoes
    assert "Jogo associado automaticamente" in relatorios


def test_plano_jogo_usa_apenas_convocados_e_tres_cincos():
    rota = (ROOT / "backend" / "routers" / "jogos.py").read_text(encoding="utf-8")
    template = (ROOT / "frontend" / "templates" / "scouting" / "plano_jogo.html").read_text(encoding="utf-8")

    assert "convocados_plano(jogo)" in rota
    assert "jogador_id not in convocados_ids" in rota
    assert "for grupo in range(1,4)" in template
    assert "A convocatória ainda está vazia" in template
    assert 'name="rotacoes"' not in template


def test_plano_jogo_tem_biblioteca_ordenada_e_jogadas_da_equipa():
    modelo = (ROOT / "backend" / "models" / "jogo.py").read_text(encoding="utf-8")
    rota = (ROOT / "backend" / "routers" / "jogos.py").read_text(encoding="utf-8")
    template = (ROOT / "frontend" / "templates" / "scouting" / "plano_jogo.html").read_text(encoding="utf-8")
    biblioteca = (ROOT / "frontend" / "templates" / "jogos" / "_plano_biblioteca.html").read_text(encoding="utf-8")

    assert 'class ItemPlanoJogoBiblioteca' in modelo
    assert 'class PlanoJogoJogada' in modelo
    assert 'Playbook.equipa_id == jogo.equipa_id' in rota
    assert 'include "jogos/_plano_biblioteca.html"' in template
    assert '/plano/itens/{{ relacao.id }}/mover/cima' in biblioteca
    assert '/plano/jogadas/{{ relacao.id }}/mover/baixo' in biblioteca


def test_previsualizacao_jogada_compoe_desenho_transparente_sobre_campo():
    desenho = Image.new("RGBA", (120, 100), (0, 0, 0, 0))
    desenho.putpixel((60, 50), (255, 0, 0, 255))
    buffer = BytesIO()
    desenho.save(buffer, format="PNG")
    data_uri = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
    jogada = SimpleNamespace(passos=[SimpleNamespace(desenho=data_uri, imagem_coach=None)])

    preview = preview_jogada(jogada)

    assert preview and preview.startswith("data:image/png;base64,")
    with Image.open(BytesIO(base64.b64decode(preview.split(",", 1)[1]))) as imagem:
        assert imagem.width > desenho.width
        assert imagem.getpixel((0, 0))[3] == 255

    jogada.passos[0].imagem_coach = data_uri
    assert preview_jogada(jogada) == data_uri


def test_biblioteca_e_usada_nos_dois_acessos_e_mantem_memoria():
    direto = (ROOT / "frontend" / "templates" / "jogos" / "plano_jogo.html").read_text(encoding="utf-8")
    scouting = (ROOT / "frontend" / "templates" / "scouting" / "plano_jogo.html").read_text(encoding="utf-8")
    biblioteca = (ROOT / "frontend" / "templates" / "jogos" / "_plano_biblioteca.html").read_text(encoding="utf-8")
    rota = (ROOT / "backend" / "routers" / "jogos.py").read_text(encoding="utf-8")

    assert 'include "jogos/_plano_biblioteca.html"' in direto
    assert 'include "jogos/_plano_biblioteca.html"' in scouting
    assert 'name="chaves_ataque"' not in direto
    assert 'name="bloqueio_direto_lateral"' not in direto
    assert "Escolher da memória da equipa" in biblioteca
    assert "Criar e guardar uma nova opção" in biblioteca
    assert "Apagar da memória da equipa" in biblioteca
    assert '/plano/biblioteca/{{ item.id }}/eliminar' in biblioteca
    assert 'item.ativo = False' in rota


def test_pdfs_colocam_rotacoes_e_graficos_no_final():
    direto = (ROOT / "frontend" / "templates" / "jogos" / "plano_jogo_print.html").read_text(encoding="utf-8")
    completo = (ROOT / "frontend" / "templates" / "relatorios" / "_documento.html").read_text(encoding="utf-8")
    facil = (ROOT / "frontend" / "templates" / "relatorios" / "plano_jogo_facil.html").read_text(encoding="utf-8")
    poster = (ROOT / "frontend" / "templates" / "relatorios" / "_poster.html").read_text(encoding="utf-8")

    for documento in (direto, completo, facil, poster):
        assert "rotacoes_equipa" in documento
        assert "graficos_plano" in documento
        assert documento.index("rotacoes_equipa") < documento.index("graficos_plano")

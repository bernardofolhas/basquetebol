from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

from services.plano_jogo_service import jogo_em_preparacao, jogos_em_preparacao


ROOT = Path(__file__).resolve().parents[2]


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

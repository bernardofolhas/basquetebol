from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


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

    assert 'class ItemPlanoJogoBiblioteca' in modelo
    assert 'class PlanoJogoJogada' in modelo
    assert 'Playbook.equipa_id == jogo.equipa_id' in rota
    assert '/plano/itens/{{ relacao.id }}/mover/cima' in template
    assert '/plano/jogadas/{{ relacao.id }}/mover/baixo' in template


def test_pdfs_colocam_rotacoes_e_graficos_no_final():
    direto = (ROOT / "frontend" / "templates" / "jogos" / "plano_jogo_print.html").read_text(encoding="utf-8")
    completo = (ROOT / "frontend" / "templates" / "relatorios" / "_documento.html").read_text(encoding="utf-8")
    facil = (ROOT / "frontend" / "templates" / "relatorios" / "plano_jogo_facil.html").read_text(encoding="utf-8")
    poster = (ROOT / "frontend" / "templates" / "relatorios" / "_poster.html").read_text(encoding="utf-8")

    for documento in (direto, completo, facil, poster):
        assert "rotacoes_equipa" in documento
        assert "graficos_plano" in documento
        assert documento.index("rotacoes_equipa") < documento.index("graficos_plano")

from pathlib import Path


def test_convocatoria_tem_edicao_reforcos_e_limite_de_doze_atletas():
    raiz = Path(__file__).resolve().parents[2]
    detalhe = (raiz / "frontend/templates/jogos/detalhe.html").read_text(encoding="utf-8")
    router = (raiz / "backend/routers/jogos.py").read_text(encoding="utf-8")

    assert "Editar convocatória" in detalhe
    assert "Escalão imediatamente abaixo" in detalhe
    assert "jogador.equipa_id != jogo.equipa_id" in detalhe
    assert "excede_limite = len(jogadores_ids) > 12" in router
    assert "jogadores_ids = jogadores_ids[:12]" in router


def test_documento_da_convocatoria_numera_a_lista_e_lista_observacoes():
    raiz = Path(__file__).resolve().parents[2]
    documento = (raiz / "frontend/templates/jogos/convocatoria_print.html").read_text(encoding="utf-8")

    assert "{{ loop.index }}" in documento
    assert "jogadores_convocados[:12]" in documento
    assert "observacoes.splitlines()" in documento
    assert "nome_clube ~ ' · Convocatória'" in documento

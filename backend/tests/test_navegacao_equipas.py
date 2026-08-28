from pathlib import Path


def test_seletor_de_equipas_no_cabecalho_abre_o_resumo():
    raiz = Path(__file__).resolve().parents[2]
    navbar = (raiz / "frontend/templates/partials/navbar_global.html").read_text(
        encoding="utf-8"
    )

    assert '/equipas/{{ item.id }}/resumo' in navbar
    assert '/planeamento/equipas/{{ item.id }}/anuais' not in navbar.split(
        'ds-team-switcher', maxsplit=1
    )[1]

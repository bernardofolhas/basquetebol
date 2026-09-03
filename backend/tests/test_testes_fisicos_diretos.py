from datetime import date

from database import SessionLocal
from models.equipa import Equipa, EscalaoEnum, GeneroEnum
from models.fisico import PlaneamentoFisico, TesteFisico as ModeloTesteFisico
from models.jogador import Jogador
from models.utilizador import Utilizador


def _criar_equipa():
    db = SessionLocal()
    clube_id = db.query(Utilizador.clube_id).filter(Utilizador.username == "admin").scalar()
    equipa = Equipa(
        clube_id=clube_id,
        nome="Equipa Testes Físicos Diretos",
        escalao=EscalaoEnum.senior,
        genero=GeneroEnum.masculino,
    )
    jogadores = [
        Jogador(clube_id=clube_id, equipa=equipa, nome="Atleta Físico Um", numero_camisola=4),
        Jogador(clube_id=clube_id, equipa=equipa, nome="Atleta Físico Dois", numero_camisola=8),
    ]
    db.add_all([equipa, *jogadores])
    db.commit()
    return db, equipa.id, [jogador.id for jogador in jogadores]


def _limpar(db, equipa_id):
    jogadores_ids = [item[0] for item in db.query(Jogador.id).filter(Jogador.equipa_id == equipa_id).all()]
    if jogadores_ids:
        db.query(ModeloTesteFisico).filter(ModeloTesteFisico.jogador_id.in_(jogadores_ids)).delete(synchronize_session=False)
    db.query(PlaneamentoFisico).filter(PlaneamentoFisico.equipa_id == equipa_id).delete(synchronize_session=False)
    db.query(Jogador).filter(Jogador.equipa_id == equipa_id).delete(synchronize_session=False)
    equipa = db.query(Equipa).filter(Equipa.id == equipa_id).first()
    if equipa:
        db.delete(equipa)
    db.commit()
    db.close()


def test_area_fisica_abre_nos_testes_sem_planeamento(client_admin):
    db, equipa_id, jogadores_ids = _criar_equipa()
    try:
        assert db.query(PlaneamentoFisico).filter(PlaneamentoFisico.equipa_id == equipa_id).count() == 0
        resposta = client_admin.get(f"/fisico/equipas/{equipa_id}")
        assert resposta.status_code == 200
        assert "Registar teste físico" in resposta.text
        assert "Não é necessário criar qualquer planeamento" in resposta.text
        assert f'name="resultado_{jogadores_ids[0]}"' in resposta.text
    finally:
        _limpar(db, equipa_id)


def test_criacao_direta_guarda_resultados_para_varios_atletas(client_admin):
    db, equipa_id, jogadores_ids = _criar_equipa()
    try:
        resposta = client_admin.post(
            f"/fisico/equipas/{equipa_id}/testes",
            data={
                "data": "2042-03-10",
                "tipo_teste": "Sprint 20 m",
                "unidade": "s",
                "observacoes": "Piso seco",
                "jogador_ids": [str(item) for item in jogadores_ids],
                f"resultado_{jogadores_ids[0]}": "3,21",
                f"resultado_{jogadores_ids[1]}": "3.35",
            },
            follow_redirects=False,
        )
        assert resposta.status_code == 303
        assert resposta.headers["location"] == f"/fisico/equipas/{equipa_id}#testes-fisicos"
        db.expire_all()
        testes = db.query(ModeloTesteFisico).filter(ModeloTesteFisico.jogador_id.in_(jogadores_ids)).order_by(ModeloTesteFisico.jogador_id).all()
        assert len(testes) == 2
        assert {teste.resultado for teste in testes} == {3.21, 3.35}
        assert all(teste.clube_id for teste in testes)
        assert all(teste.data == date(2042, 3, 10) for teste in testes)
    finally:
        _limpar(db, equipa_id)


def test_criacao_direta_rejeita_resultado_invalido(client_admin):
    db, equipa_id, jogadores_ids = _criar_equipa()
    try:
        resposta = client_admin.post(
            f"/fisico/equipas/{equipa_id}/testes",
            data={
                "data": "2042-03-10",
                "tipo_teste": "CMJ",
                "jogador_ids": str(jogadores_ids[0]),
                f"resultado_{jogadores_ids[0]}": "inválido",
            },
            follow_redirects=False,
        )
        assert resposta.status_code == 303
        assert db.query(ModeloTesteFisico).filter(ModeloTesteFisico.jogador_id == jogadores_ids[0]).count() == 0
    finally:
        _limpar(db, equipa_id)


def test_planeamento_fisico_continua_disponivel_como_opcao(client_admin):
    db, equipa_id, _ = _criar_equipa()
    try:
        pagina = client_admin.get(f"/fisico/equipas/{equipa_id}?vista=planeamento")
        assert pagina.status_code == 200
        assert "Este planeamento organiza conteúdos" in pagina.text

        resposta = client_admin.post(
            f"/fisico/equipas/{equipa_id}/novo",
            data={
                "data_inicio": "2042-03-01",
                "data_fim": "2042-03-31",
                "tipo": "Mensal",
                "resistencia": "Capacidade aeróbia",
            },
            follow_redirects=False,
        )
        assert resposta.status_code == 303
        assert resposta.headers["location"] == f"/fisico/equipas/{equipa_id}?vista=planeamento"
        plano = db.query(PlaneamentoFisico).filter(PlaneamentoFisico.equipa_id == equipa_id).one()
        assert plano.clube_id
    finally:
        _limpar(db, equipa_id)

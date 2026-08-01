from datetime import date

from database import SessionLocal
from models.assiduidade import RegistoAssiduidade
from models.equipa import Equipa, EscalaoEnum, GeneroEnum
from models.fisico import TesteFisico as ModeloTesteFisico
from models.jogador import Jogador, RegistoAntropometrico
from models.planeamento import Macrociclo, Mesociclo, Microciclo, SessaoTreino
from services.assiduidade_service import calcular_resumo_assiduidade


def _criar_contexto():
    db = SessionLocal()
    equipa = Equipa(
        nome="Equipa Fase 2 Assiduidade",
        escalao=EscalaoEnum.sub18,
        genero=GeneroEnum.feminino,
    )
    jogadora = Jogador(nome="Jogadora Fase 2", equipa=equipa, numero_camisola=7)
    segunda_jogadora = Jogador(nome="Segunda Jogadora Fase 2", equipa=equipa)
    macro = Macrociclo(
        numero=1,
        data_inicio=date(2037, 1, 1),
        data_fim=date(2037, 12, 31),
        equipa=equipa,
    )
    meso = Mesociclo(
        numero=1,
        data_inicio=date(2037, 1, 1),
        data_fim=date(2037, 3, 31),
        macrociclo=macro,
    )
    micro = Microciclo(
        numero=1,
        data_inicio=date(2037, 1, 4),
        data_fim=date(2037, 1, 10),
        mesociclo=meso,
    )
    sessao = SessaoTreino(
        data=date(2037, 1, 6),
        local="Pavilhão Fase 2",
        estado="executada",
        ativa=True,
        microciclo=micro,
    )
    db.add_all([equipa, jogadora, segunda_jogadora, macro, meso, micro, sessao])
    db.flush()
    db.add_all([
        RegistoAssiduidade(
            sessao_id=sessao.id,
            jogador_id=jogadora.id,
            presente=True,
            estado="presente",
        ),
        RegistoAssiduidade(
            sessao_id=sessao.id,
            jogador_id=segunda_jogadora.id,
            presente=False,
            estado="justificada",
            motivo_falta="Consulta médica",
        ),
        RegistoAntropometrico(
            jogador_id=jogadora.id,
            data=date(2037, 1, 5),
            altura=172,
            peso=61,
            envergadura=175,
        ),
        ModeloTesteFisico(
            jogador_id=jogadora.id,
            data=date(2037, 1, 5),
            tipo_teste="Sprint 20m",
            resultado=3.4,
            unidade="s",
        ),
    ])
    db.commit()
    return db, equipa.id, jogadora.id, segunda_jogadora.id, macro.id


def _limpar_contexto(db, equipa_id, jogadora_id, segunda_jogadora_id, macro_id):
    db.query(RegistoAssiduidade).filter(
        RegistoAssiduidade.jogador_id.in_([jogadora_id, segunda_jogadora_id])
    ).delete(synchronize_session=False)
    db.query(RegistoAntropometrico).filter(
        RegistoAntropometrico.jogador_id == jogadora_id
    ).delete(synchronize_session=False)
    db.query(ModeloTesteFisico).filter(ModeloTesteFisico.jogador_id == jogadora_id).delete(synchronize_session=False)
    macro = db.query(Macrociclo).filter(Macrociclo.id == macro_id).first()
    if macro:
        db.delete(macro)
    for jogador_id in (jogadora_id, segunda_jogadora_id):
        jogador = db.query(Jogador).filter(Jogador.id == jogador_id).first()
        if jogador:
            db.delete(jogador)
    equipa = db.query(Equipa).filter(Equipa.id == equipa_id).first()
    if equipa:
        db.delete(equipa)
    db.commit()


def test_calcula_estados_detalhados_sem_perder_compatibilidade_booleana():
    registos = [
        RegistoAssiduidade(presente=True, estado="presente"),
        RegistoAssiduidade(presente=True, estado="atrasada"),
        RegistoAssiduidade(presente=False, estado="lesionada"),
    ]
    resumo = calcular_resumo_assiduidade(registos)
    assert resumo["total"] == 3
    assert resumo["presentes"] == 2
    assert resumo["por_estado"]["atrasada"] == 1
    assert resumo["por_estado"]["lesionada"] == 1
    assert resumo["percentagem"] == 66.7


def test_relatorio_assiduidade_e_ficha_evolucao_respondem_com_pdf(client_admin):
    db, equipa_id, jogadora_id, segunda_jogadora_id, macro_id = _criar_contexto()
    try:
        resposta = client_admin.get(f"/assiduidade/equipas/{equipa_id}?inicio=2037-01-01&fim=2037-01-31")
        assert resposta.status_code == 200
        assert "Resumo por jogadora" in resposta.text
        assert "Jogadora Fase 2" in resposta.text
        assert "Faltas justificadas" in resposta.text

        pdf = client_admin.get(f"/assiduidade/equipas/{equipa_id}/pdf?inicio=2037-01-01&fim=2037-01-31")
        assert pdf.status_code == 200
        assert pdf.headers["content-type"] == "application/pdf"
        assert pdf.content.startswith(b"%PDF")

        detalhe = client_admin.get(f"/jogadores/{jogadora_id}")
        assert detalhe.status_code == 200
        assert "Ficha de evolução" in detalhe.text
        assert "Sprint 20m" in detalhe.text

        ficha_pdf = client_admin.get(f"/jogadores/{jogadora_id}/evolucao/pdf")
        assert ficha_pdf.status_code == 200
        assert ficha_pdf.content.startswith(b"%PDF")
    finally:
        _limpar_contexto(db, equipa_id, jogadora_id, segunda_jogadora_id, macro_id)
        db.close()


def test_formulario_guarda_estado_detalhado_e_mantem_presente(client_admin):
    db, equipa_id, jogadora_id, segunda_jogadora_id, macro_id = _criar_contexto()
    sessao_id = db.query(SessaoTreino).join(Microciclo).join(Mesociclo).join(Macrociclo).filter(
        Macrociclo.id == macro_id
    ).first().id
    try:
        resposta = client_admin.post(
            f"/assiduidade/sessoes/{sessao_id}",
            data={
                f"estado_{jogadora_id}": "atrasada",
                f"motivo_{jogadora_id}": "Chegou depois do início",
                f"estado_{segunda_jogadora_id}": "lesionada",
                f"motivo_{segunda_jogadora_id}": "Dor no tornozelo",
            },
            follow_redirects=False,
        )
        assert resposta.status_code == 303
        registo = db.query(RegistoAssiduidade).filter(
            RegistoAssiduidade.sessao_id == sessao_id,
            RegistoAssiduidade.jogador_id == jogadora_id,
        ).first()
        segundo_registo = db.query(RegistoAssiduidade).filter(
            RegistoAssiduidade.sessao_id == sessao_id,
            RegistoAssiduidade.jogador_id == segunda_jogadora_id,
        ).first()
        assert registo.estado == "atrasada"
        assert registo.presente is True
        assert segundo_registo.estado == "lesionada"
        assert segundo_registo.presente is False
    finally:
        _limpar_contexto(db, equipa_id, jogadora_id, segunda_jogadora_id, macro_id)
        db.close()


def test_abrir_assiduidade_nao_cria_faltas_automaticamente(client_admin):
    db, equipa_id, jogadora_id, segunda_jogadora_id, macro_id = _criar_contexto()
    sessao = db.query(SessaoTreino).join(Microciclo).join(Mesociclo).join(Macrociclo).filter(
        Macrociclo.id == macro_id
    ).first()
    try:
        antes = db.query(RegistoAssiduidade).filter(RegistoAssiduidade.sessao_id == sessao.id).count()
        resposta = client_admin.get(f"/assiduidade/sessoes/{sessao.id}")
        depois = db.query(RegistoAssiduidade).filter(RegistoAssiduidade.sessao_id == sessao.id).count()

        assert resposta.status_code == 200
        assert antes == 2
        assert depois == antes
        assert "Por registar" in resposta.text
    finally:
        _limpar_contexto(db, equipa_id, jogadora_id, segunda_jogadora_id, macro_id)
        db.close()

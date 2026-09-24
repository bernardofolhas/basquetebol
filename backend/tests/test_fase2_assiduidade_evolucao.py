from datetime import date

from database import SessionLocal
from models.assiduidade import ConvocacaoAssiduidade, RegistoAssiduidade
from models.equipa import Equipa, EscalaoEnum, GeneroEnum
from models.fisico import TesteFisico as ModeloTesteFisico
from models.jogador import Jogador, RegistoAntropometrico
from models.planeamento import Macrociclo, Mesociclo, Microciclo, SessaoTreino
from models.utilizador import Utilizador
from services.assiduidade_service import (
    calcular_pse_real,
    calcular_resumo_assiduidade,
    estados_assiduidade_visuais,
)
from services.carga_real_service import analisar_carga_jogador, analisar_carga_sessoes
import routers.assiduidade as assiduidade_router


def _criar_contexto():
    db = SessionLocal()
    clube_id = db.query(Utilizador.clube_id).filter(Utilizador.username == "admin").scalar()
    assert clube_id is not None
    equipa = Equipa(
        clube_id=clube_id,
        nome="Equipa Fase 2 Assiduidade",
        escalao=EscalaoEnum.sub18,
        genero=GeneroEnum.feminino,
    )
    jogadora = Jogador(clube_id=clube_id, nome="Jogadora Fase 2", equipa=equipa, numero_camisola=7)
    segunda_jogadora = Jogador(clube_id=clube_id, nome="Segunda Jogadora Fase 2", equipa=equipa)
    macro = Macrociclo(
        clube_id=clube_id,
        numero=1,
        data_inicio=date(2037, 1, 1),
        data_fim=date(2037, 12, 31),
        equipa=equipa,
    )
    meso = Mesociclo(
        clube_id=clube_id,
        numero=1,
        data_inicio=date(2037, 1, 1),
        data_fim=date(2037, 3, 31),
        macrociclo=macro,
    )
    micro = Microciclo(
        clube_id=clube_id,
        numero=1,
        data_inicio=date(2037, 1, 4),
        data_fim=date(2037, 1, 10),
        mesociclo=meso,
    )
    sessao = SessaoTreino(
        clube_id=clube_id,
        data=date(2037, 1, 6),
        local="Pavilhão Fase 2",
        hora_inicio="18:00",
        hora_fim="19:30",
        estado="executada",
        ativa=True,
        volume_minutos=90,
        intensidade_rpe=6,
        microciclo=micro,
    )
    db.add_all([equipa, jogadora, segunda_jogadora, macro, meso, micro, sessao])
    db.flush()
    db.add_all([
        RegistoAssiduidade(
            clube_id=clube_id,
            sessao_id=sessao.id,
            jogador_id=jogadora.id,
            presente=True,
            estado="presente",
            rpe_individual=7.5,
        ),
        RegistoAssiduidade(
            clube_id=clube_id,
            sessao_id=sessao.id,
            jogador_id=segunda_jogadora.id,
            presente=False,
            estado="justificada",
            motivo_falta="Consulta médica",
        ),
        RegistoAntropometrico(
            clube_id=clube_id,
            jogador_id=jogadora.id,
            data=date(2037, 1, 5),
            altura=172,
            peso=61,
            envergadura=175,
        ),
        ModeloTesteFisico(
            clube_id=clube_id,
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
        RegistoAssiduidade(presente=True, estado="presente", rpe_individual=7),
        RegistoAssiduidade(presente=True, estado="atrasada", rpe_individual=8),
        RegistoAssiduidade(presente=False, estado="lesionada"),
    ]
    resumo = calcular_resumo_assiduidade(registos)
    assert resumo["total"] == 3
    assert resumo["presentes"] == 2
    assert resumo["por_estado"]["atrasada"] == 1
    assert resumo["por_estado"]["lesionada"] == 1
    assert resumo["percentagem"] == 66.7
    assert resumo["rpe_medio"] == 7.5
    assert resumo["rpe_registados"] == 2


def test_lesionado_conta_como_presenca_e_lesionado_falta_como_ausencia():
    resumo = calcular_resumo_assiduidade([
        RegistoAssiduidade(presente=True, estado="lesionado", rpe_individual=4),
        RegistoAssiduidade(presente=False, estado="lesionada"),
    ])

    assert resumo["presentes"] == 1
    assert resumo["por_estado"]["lesionado"] == 1
    assert resumo["por_estado"]["lesionada"] == 1
    assert resumo["percentagem"] == 50.0
    assert resumo["rpe_medio"] == 4.0


def test_etiquetas_de_assiduidade_respeitam_genero_da_equipa():
    masculina = Equipa(genero=GeneroEnum.masculino)
    feminina = Equipa(genero=GeneroEnum.feminino)

    etiquetas_masculinas = estados_assiduidade_visuais(masculina)
    etiquetas_femininas = estados_assiduidade_visuais(feminina)

    assert etiquetas_masculinas["atrasada"]["label"] == "Atrasado"
    assert etiquetas_masculinas["lesionado"]["label"] == "Lesionado"
    assert etiquetas_masculinas["lesionada"]["label"] == "Lesionado + Falta"
    assert etiquetas_masculinas["dispensada"]["label"] == "Dispensado"
    assert etiquetas_femininas["lesionado"]["label"] == "Lesionada"
    assert etiquetas_femininas["lesionada"]["label"] == "Lesionada + Falta"


def test_folha_de_assiduidade_masculina_apresenta_estados_no_masculino(client_admin):
    db, equipa_id, jogadora_id, segunda_jogadora_id, macro_id = _criar_contexto()
    try:
        equipa = db.query(Equipa).filter(Equipa.id == equipa_id).one()
        equipa.genero = GeneroEnum.masculino
        db.commit()
        sessao_id = db.query(SessaoTreino).join(Microciclo).join(Mesociclo).join(Macrociclo).filter(
            Macrociclo.id == macro_id
        ).first().id

        resposta = client_admin.get(f"/assiduidade/sessoes/{sessao_id}")

        assert resposta.status_code == 200
        assert ">Atrasado<" in resposta.text
        assert ">Lesionado<" in resposta.text
        assert ">Lesionado + Falta<" in resposta.text
        assert ">Dispensado<" in resposta.text
        assert ">Lesionada<" not in resposta.text
    finally:
        _limpar_contexto(db, equipa_id, jogadora_id, segunda_jogadora_id, macro_id)
        db.close()


def test_rpe_pos_treino_alimenta_carga_real_dos_ciclos_e_do_atleta():
    db, equipa_id, jogadora_id, segunda_jogadora_id, macro_id = _criar_contexto()
    try:
        sessao = db.query(SessaoTreino).join(Microciclo).join(Mesociclo).join(Macrociclo).filter(
            Macrociclo.id == macro_id
        ).one()

        ciclo = analisar_carga_sessoes(db, [sessao])
        atleta = analisar_carga_jogador(db, jogadora_id)

        assert ciclo["intensidade_real"] == 7.5
        assert ciclo["carga_real"] == 675
        assert ciclo["carga_planeada_comparavel"] == 540
        assert ciclo["desvio_carga"] == 135
        assert ciclo["cobertura"] == 100
        assert atleta["intensidade_media"] == 7.5
        assert atleta["carga_total"] == 675
    finally:
        _limpar_contexto(db, equipa_id, jogadora_id, segunda_jogadora_id, macro_id)
        db.close()


def test_dispensa_nao_e_falta_nem_reduz_a_percentagem_de_presencas():
    resumo = calcular_resumo_assiduidade([
        RegistoAssiduidade(presente=True, estado="presente"),
        RegistoAssiduidade(presente=False, estado="dispensada"),
        RegistoAssiduidade(presente=False, estado="ausente"),
    ])

    assert resumo["total"] == 3
    assert resumo["total_elegivel"] == 2
    assert resumo["por_estado"]["dispensada"] == 1
    assert resumo["percentagem"] == 50.0


def test_relatorio_assiduidade_e_ficha_evolucao_respondem_com_pdf(client_admin):
    db, equipa_id, jogadora_id, segunda_jogadora_id, macro_id = _criar_contexto()
    try:
        resposta = client_admin.get(f"/assiduidade/equipas/{equipa_id}?inicio=2037-01-01&fim=2037-01-31")
        assert resposta.status_code == 200
        assert "Escolhe uma sessão para registar" in resposta.text
        assert 'data-workspace-tab="registar"' in resposta.text
        assert 'data-workspace-panel="assiduidade:analise"' in resposta.text
        assert "ds-attendance-session-row" in resposta.text
        assert f"/assiduidade/sessoes/" in resposta.text
        assert "Resumo por jogadora" in resposta.text
        assert "Jogadora Fase 2" in resposta.text
        assert "Justificadas" in resposta.text

        acesso_direto = client_admin.get(
            f"/assiduidade/equipas/{equipa_id}/registar",
            follow_redirects=False,
        )
        assert acesso_direto.status_code == 303
        assert acesso_direto.headers["location"].startswith("/assiduidade/sessoes/")

        folha = client_admin.get(acesso_direto.headers["location"])
        assert folha.status_code == 200
        assert 'aria-label="Selecionar sessão de treino"' in folha.text
        assert f'/assiduidade/equipas/{equipa_id}"' in folha.text

        pdf = client_admin.get(f"/assiduidade/equipas/{equipa_id}/pdf?inicio=2037-01-01&fim=2037-01-31")
        assert pdf.status_code == 200
        assert pdf.headers["content-type"] == "application/pdf"
        assert pdf.content.startswith(b"%PDF")

        detalhe = client_admin.get(f"/jogadores/{jogadora_id}")
        assert detalhe.status_code == 200
        assert "Ficha de evolução" in detalhe.text
        assert "Sprint 20m" in detalhe.text
        assert "Intensidade real" in detalhe.text
        assert "Carga real por treino" in detalhe.text

        micro = db.query(Microciclo).join(Mesociclo).join(Macrociclo).filter(Macrociclo.id == macro_id).one()
        pagina_micro = client_admin.get(f"/planeamento/microciclos/{micro.id}")
        assert pagina_micro.status_code == 200
        assert "Intensidade e carga reais" in pagina_micro.text
        assert "RPE real média" in pagina_micro.text

        pagina_meso = client_admin.get(f"/planeamento/mesociclos/{micro.mesociclo_id}")
        assert pagina_meso.status_code == 200
        assert "Intensidade real do mesociclo" in pagina_meso.text
        assert 'data-workspace-tab="carga"' in pagina_meso.text

        analise_atleta = client_admin.get(f"/analise/jogadores/{jogadora_id}")
        assert analise_atleta.status_code == 200
        assert "Intensidade real dos treinos" in analise_atleta.text
        assert "Carga acumulada" in analise_atleta.text

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
                f"rpe_{jogadora_id}": "8,5",
                f"estado_{segunda_jogadora_id}": "lesionada",
                f"motivo_{segunda_jogadora_id}": "Dor no tornozelo",
                f"rpe_{segunda_jogadora_id}": "9",
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
        assert registo.rpe_individual == 8.5
        assert segundo_registo.estado == "lesionada"
        assert segundo_registo.presente is False
        assert segundo_registo.rpe_individual is None
    finally:
        _limpar_contexto(db, equipa_id, jogadora_id, segunda_jogadora_id, macro_id)
        db.close()


def test_pse_rapida_abre_treino_do_dia_e_guarda_valores_individuais(client_admin, monkeypatch):
    db, equipa_id, jogadora_id, segunda_jogadora_id, macro_id = _criar_contexto()
    sessao_id = db.query(SessaoTreino).join(Microciclo).join(Mesociclo).join(Macrociclo).filter(
        Macrociclo.id == macro_id
    ).first().id

    class DataDoTreino:
        @classmethod
        def today(cls):
            return date(2037, 1, 6)

        @classmethod
        def fromisoformat(cls, valor):
            return date.fromisoformat(valor)

    monkeypatch.setattr(assiduidade_router, "date", DataDoTreino)
    try:
        pagina = client_admin.get(f"/assiduidade/equipas/{equipa_id}/pse")
        assert pagina.status_code == 200
        assert "PSE individual" in pagina.text
        assert "Treino de hoje" in pagina.text
        assert f'data-player-id="{jogadora_id}"' in pagina.text
        assert "pse-player-card" in pagina.text
        assert 'id="pse-entry-dialog"' in pagina.text
        assert "fetch(form.action" in pagina.text
        assert "select.value" not in pagina.text

        resposta = client_admin.post(
            f"/assiduidade/sessoes/{sessao_id}/pse",
            data={f"rpe_{segunda_jogadora_id}": "8"},
            headers={
                "Accept": "application/json",
                "X-Requested-With": "XMLHttpRequest",
            },
        )
        assert resposta.status_code == 200
        dados = resposta.json()
        assert dados["sucesso"] is True
        assert dados["jogador_id"] == segunda_jogadora_id
        assert dados["rpe"] == 8
        assert dados["total_preenchidos"] == 2
        assert dados["total_jogadores"] == 2
        db.expire_all()
        assert calcular_pse_real(db.query(RegistoAssiduidade).filter(
            RegistoAssiduidade.sessao_id == sessao_id,
        ).all()) == 7.8

        resposta = client_admin.post(
            f"/assiduidade/sessoes/{sessao_id}/pse",
            data={f"rpe_{jogadora_id}": "8,5", f"rpe_{segunda_jogadora_id}": ""},
            follow_redirects=False,
        )
        assert resposta.status_code == 303
        registo = db.query(RegistoAssiduidade).filter(
            RegistoAssiduidade.sessao_id == sessao_id,
            RegistoAssiduidade.jogador_id == jogadora_id,
        ).one()
        assert registo.rpe_individual == 8.5
        registo.estado = "lesionado"
        registo.presente = True
        db.commit()

        resposta = client_admin.post(
            f"/assiduidade/sessoes/{sessao_id}/pse",
            data={f"rpe_{jogadora_id}": "9"},
            follow_redirects=False,
        )
        assert resposta.status_code == 303
        db.expire_all()
        registo = db.query(RegistoAssiduidade).filter(
            RegistoAssiduidade.sessao_id == sessao_id,
            RegistoAssiduidade.jogador_id == jogadora_id,
        ).one()
        assert registo.rpe_individual == 9
        assert registo.estado == "lesionado"
        assert registo.presente is True
    finally:
        _limpar_contexto(db, equipa_id, jogadora_id, segunda_jogadora_id, macro_id)
        db.close()


def test_convocacao_de_outro_escalao_fica_limitada_a_uma_sessao(client_admin):
    db, equipa_id, jogadora_id, segunda_jogadora_id, macro_id = _criar_contexto()
    equipa = db.query(Equipa).filter(Equipa.id == equipa_id).one()
    outra_equipa = Equipa(
        clube_id=equipa.clube_id,
        nome="Equipa Inferior Convocação",
        escalao=EscalaoEnum.sub16,
        genero=GeneroEnum.feminino,
    )
    chamada = Jogador(
        clube_id=equipa.clube_id,
        nome="Jogadora Convocada Fase 2",
        equipa=outra_equipa,
    )
    sessao_atual = db.query(SessaoTreino).join(Microciclo).join(Mesociclo).join(Macrociclo).filter(
        Macrociclo.id == macro_id
    ).first()
    sessao_seguinte = SessaoTreino(
        clube_id=equipa.clube_id,
        data=date(2037, 1, 7),
        local="Pavilhão seguinte",
        microciclo_id=sessao_atual.microciclo_id,
        estado="planeada",
        ativa=True,
    )
    db.add_all([outra_equipa, chamada, sessao_seguinte])
    db.flush()
    chamada_id = chamada.id
    sessao_seguinte_id = sessao_seguinte.id
    db.commit()
    try:
        resposta = client_admin.post(
            f"/assiduidade/sessoes/{sessao_atual.id}/convocados",
            data={"jogador_id": str(chamada_id)},
            follow_redirects=False,
        )
        assert resposta.status_code == 303
        assert db.query(ConvocacaoAssiduidade).filter(
            ConvocacaoAssiduidade.sessao_id == sessao_atual.id,
            ConvocacaoAssiduidade.jogador_id == chamada_id,
        ).count() == 1

        folha = client_admin.get(f"/assiduidade/sessoes/{sessao_atual.id}")
        assert folha.status_code == 200
        assert "Jogadora Convocada Fase 2" in folha.text
        assert "Equipa Inferior Convocação" in folha.text

        dados = {
            f"estado_{jogadora_id}": "presente",
            f"estado_{segunda_jogadora_id}": "presente",
            f"estado_{chamada_id}": "presente",
            f"rpe_{chamada_id}": "8",
        }
        guardar = client_admin.post(
            f"/assiduidade/sessoes/{sessao_atual.id}",
            data=dados,
            follow_redirects=False,
        )
        assert guardar.status_code == 303
        registo_chamada = db.query(RegistoAssiduidade).filter(
            RegistoAssiduidade.sessao_id == sessao_atual.id,
            RegistoAssiduidade.jogador_id == chamada_id,
        ).one()
        assert registo_chamada.presente is True
        assert registo_chamada.rpe_individual == 8

        folha_seguinte = client_admin.get(f"/assiduidade/sessoes/{sessao_seguinte_id}")
        assert folha_seguinte.status_code == 200
        assert f'data-jogador-id="{chamada_id}"' not in folha_seguinte.text

        remover = client_admin.post(
            f"/assiduidade/sessoes/{sessao_atual.id}/convocados/{chamada_id}/eliminar",
            follow_redirects=False,
        )
        assert remover.status_code == 303
        assert db.query(ConvocacaoAssiduidade).filter(
            ConvocacaoAssiduidade.sessao_id == sessao_atual.id,
            ConvocacaoAssiduidade.jogador_id == chamada_id,
        ).count() == 0
        assert db.query(RegistoAssiduidade).filter(
            RegistoAssiduidade.sessao_id == sessao_atual.id,
            RegistoAssiduidade.jogador_id == chamada_id,
        ).count() == 0
    finally:
        db.query(ConvocacaoAssiduidade).filter(
            ConvocacaoAssiduidade.jogador_id == chamada_id,
        ).delete(synchronize_session=False)
        db.query(RegistoAssiduidade).filter(
            RegistoAssiduidade.jogador_id == chamada_id,
        ).delete(synchronize_session=False)
        db.delete(sessao_seguinte)
        db.delete(chamada)
        db.delete(outra_equipa)
        db.commit()
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
        assert "RPE individual" in resposta.text
        assert "data-attendance-row" in resposta.text
        assert "18:00" in resposta.text

        plano = client_admin.get(f"/treino/sessoes/{sessao.id}")
        assert plano.status_code == 200
        link_assiduidade = f'/assiduidade/sessoes/{sessao.id}'
        assert link_assiduidade in plano.text
        assert "Abrir assiduidade" in plano.text
        assert plano.text.index(link_assiduidade) < plano.text.index('ds-page-actions')
    finally:
        _limpar_contexto(db, equipa_id, jogadora_id, segunda_jogadora_id, macro_id)
        db.close()


def test_rpe_individual_invalido_nao_altera_o_registo(client_admin):
    db, equipa_id, jogadora_id, segunda_jogadora_id, macro_id = _criar_contexto()
    sessao_id = db.query(SessaoTreino).join(Microciclo).join(Mesociclo).join(Macrociclo).filter(
        Macrociclo.id == macro_id
    ).first().id
    try:
        resposta = client_admin.post(
            f"/assiduidade/sessoes/{sessao_id}",
            data={
                f"estado_{jogadora_id}": "presente",
                f"rpe_{jogadora_id}": "11",
                f"estado_{segunda_jogadora_id}": "presente",
            },
            follow_redirects=False,
        )
        assert resposta.status_code == 303
        db.expire_all()
        registo = db.query(RegistoAssiduidade).filter(
            RegistoAssiduidade.sessao_id == sessao_id,
            RegistoAssiduidade.jogador_id == jogadora_id,
        ).first()
        assert registo.rpe_individual == 7.5
    finally:
        _limpar_contexto(db, equipa_id, jogadora_id, segunda_jogadora_id, macro_id)
        db.close()


def test_guardar_cria_registo_com_rpe_e_clube_correto(client_admin):
    db, equipa_id, jogadora_id, segunda_jogadora_id, macro_id = _criar_contexto()
    sessao = db.query(SessaoTreino).join(Microciclo).join(Mesociclo).join(Macrociclo).filter(
        Macrociclo.id == macro_id
    ).first()
    try:
        db.query(RegistoAssiduidade).filter(
            RegistoAssiduidade.sessao_id == sessao.id,
            RegistoAssiduidade.jogador_id == segunda_jogadora_id,
        ).delete(synchronize_session=False)
        db.commit()

        resposta = client_admin.post(
            f"/assiduidade/sessoes/{sessao.id}",
            data={
                f"estado_{jogadora_id}": "presente",
                f"rpe_{jogadora_id}": "7",
                f"estado_{segunda_jogadora_id}": "presente",
                f"rpe_{segunda_jogadora_id}": "6",
            },
            follow_redirects=False,
        )
        assert resposta.status_code == 303
        criado = db.query(RegistoAssiduidade).filter(
            RegistoAssiduidade.sessao_id == sessao.id,
            RegistoAssiduidade.jogador_id == segunda_jogadora_id,
        ).first()
        assert criado is not None
        assert criado.clube_id == sessao.clube_id
        assert criado.rpe_individual == 6
    finally:
        _limpar_contexto(db, equipa_id, jogadora_id, segunda_jogadora_id, macro_id)
        db.close()


def test_limpar_estados_remove_registos_em_vez_de_criar_estados_vazios(client_admin):
    db, equipa_id, jogadora_id, segunda_jogadora_id, macro_id = _criar_contexto()
    sessao = db.query(SessaoTreino).join(Microciclo).join(Mesociclo).join(Macrociclo).filter(
        Macrociclo.id == macro_id
    ).first()
    try:
        resposta = client_admin.post(
            f"/assiduidade/sessoes/{sessao.id}",
            data={
                f"estado_{jogadora_id}": "por_registar",
                f"estado_{segunda_jogadora_id}": "por_registar",
            },
            follow_redirects=False,
        )
        assert resposta.status_code == 303
        assert db.query(RegistoAssiduidade).filter(
            RegistoAssiduidade.sessao_id == sessao.id
        ).count() == 0
    finally:
        _limpar_contexto(db, equipa_id, jogadora_id, segunda_jogadora_id, macro_id)
        db.close()

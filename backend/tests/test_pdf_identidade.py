from types import SimpleNamespace

from services import pdf_service


def _request(identidade):
    return SimpleNamespace(state=SimpleNamespace(identidade_clube=identidade))


def test_contexto_pdf_embebe_logo_local(monkeypatch, tmp_path):
    branding = tmp_path / "uploads" / "branding"
    branding.mkdir(parents=True)
    (branding / "clube.png").write_bytes(b"logo")
    monkeypatch.setattr(pdf_service, "STATIC_DIR", tmp_path)

    contexto = pdf_service.preparar_contexto_pdf(_request({
        **pdf_service.CORES_PADRAO,
        "logo_principal": "/static/uploads/branding/clube.png",
    }))

    assert contexto["identidade"]["logo_principal"] == "data:image/png;base64,bG9nbw=="


def test_contexto_pdf_descarta_logo_inacessivel(monkeypatch, tmp_path):
    monkeypatch.setattr(pdf_service, "STATIC_DIR", tmp_path)
    contexto = pdf_service.preparar_contexto_pdf(_request({
        **pdf_service.CORES_PADRAO,
        "logo_principal": "https://example.test/logo.svg",
    }))

    assert contexto["identidade"]["logo_principal"] is None


def test_contexto_pdf_abrevia_nome_do_treinador_no_rodape():
    contexto = pdf_service.preparar_contexto_pdf(
        _request(pdf_service.CORES_PADRAO),
        {"nome_treinador": "Bernardo Manuel da Silva Folhas"},
    )

    assert contexto["nome_treinador"] == "Bernardo Folhas"
    assert pdf_service.nome_curto_pessoa("Bernardo Folhas") == "Bernardo Folhas"
    assert pdf_service.nome_curto_pessoa("Bernardo") == "Bernardo"


def test_relatorios_faceis_tratam_fundo_dos_simbolos(monkeypatch):
    monkeypatch.setattr(
        pdf_service, "_identidade_para_pdf",
        lambda identidade, scouting=False: {"logo_principal": "sem-fundo" if scouting else "opaco"},
    )
    monkeypatch.setattr(pdf_service, "simbolo_cabecalho_sem_fundo", lambda uri: f"sem-fundo:{uri}")
    for tipo in ("roster", "plano-jogo", "convocatoria"):
        contexto = pdf_service.preparar_contexto_pdf(
            _request(pdf_service.CORES_PADRAO),
            {"tipo_relatorio": tipo, "formato": "facil", "simbolo_adversario": "adversario"},
        )
        assert contexto["identidade"]["logo_principal"] == "sem-fundo"
        assert contexto["simbolo_adversario"] == "sem-fundo:adversario"


def test_content_disposition_pdf_usa_nome_simples_e_preserva_acentos():
    cabecalho = pdf_service.content_disposition_pdf("Treino físico 2")

    assert 'filename="Treino fisico 2.pdf"' in cabecalho
    assert "filename*=UTF-8''Treino%20f%C3%ADsico%202.pdf" in cabecalho
    assert pdf_service.content_disposition_pdf("Microciclo 1").endswith("Microciclo%201.pdf")

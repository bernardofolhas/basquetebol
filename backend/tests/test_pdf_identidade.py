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

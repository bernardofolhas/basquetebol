from types import SimpleNamespace

from services import email_service


class RespostaAceite:
    def raise_for_status(self):
        return None


def test_envio_por_api_https_tem_prioridade_sobre_smtp(monkeypatch):
    pedidos = []

    def enviar(url, **kwargs):
        pedidos.append((url, kwargs))
        return RespostaAceite()

    monkeypatch.setattr(email_service, "config", SimpleNamespace(
        smtp_from_email="plataforma@clube.pt",
        brevo_api_key="segredo-de-teste",
        smtp_host="smtp.exemplo.pt",
    ))
    monkeypatch.setattr(email_service.httpx, "post", enviar)

    assert email_service.enviar_email("treinador@example.test", "Recuperação", "Ligação segura")
    assert len(pedidos) == 1
    url, opcoes = pedidos[0]
    assert url == "https://api.brevo.com/v3/smtp/email"
    assert opcoes["headers"]["api-key"] == "segredo-de-teste"
    assert opcoes["json"]["to"] == [{"email": "treinador@example.test"}]
    assert opcoes["json"]["textContent"] == "Ligação segura"

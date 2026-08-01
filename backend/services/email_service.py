import smtplib
from email.message import EmailMessage

import httpx

from config import config
from logging_config import obter_logger

logger = obter_logger(__name__)


def enviar_email(destinatario: str, assunto: str, texto: str) -> bool:
    """Envia email por HTTPS ou SMTP sem expor credenciais nos logs."""
    if not config.smtp_from_email or not destinatario:
        logger.warning("Email não enviado: remetente ou destinatário em falta.")
        return False

    if config.brevo_api_key:
        try:
            resposta = httpx.post(
                "https://api.brevo.com/v3/smtp/email",
                headers={
                    "accept": "application/json",
                    "api-key": config.brevo_api_key,
                    "content-type": "application/json",
                },
                json={
                    "sender": {"email": config.smtp_from_email},
                    "to": [{"email": destinatario}],
                    "subject": assunto,
                    "textContent": texto,
                },
                timeout=10,
            )
            resposta.raise_for_status()
            return True
        except Exception:
            logger.exception("Falha ao enviar email transacional pela API HTTPS.")
            return False

    if not config.smtp_host:
        logger.warning("Email não enviado: configuração SMTP incompleta.")
        return False

    mensagem = EmailMessage()
    mensagem["From"] = config.smtp_from_email
    mensagem["To"] = destinatario
    mensagem["Subject"] = assunto
    mensagem.set_content(texto)
    try:
        with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=10) as servidor:
            if config.smtp_use_tls:
                servidor.starttls()
            if config.smtp_username and config.smtp_password:
                servidor.login(config.smtp_username, config.smtp_password)
            servidor.send_message(mensagem)
        return True
    except Exception:
        logger.exception("Falha ao enviar email transacional.")
        return False

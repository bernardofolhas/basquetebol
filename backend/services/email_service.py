import smtplib
from email.message import EmailMessage

from config import config
from logging_config import obter_logger

logger = obter_logger(__name__)


def enviar_email(destinatario: str, assunto: str, texto: str) -> bool:
    """Envia email por SMTP sem expor credenciais ou conteúdo nos logs."""
    if not config.smtp_host or not config.smtp_from_email or not destinatario:
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

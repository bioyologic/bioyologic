"""Envío de correos (códigos de verificación y de recuperación de contraseña) por SMTP.

Variables de entorno:
    BIOYOLOGIC_SMTP_HOST      servidor SMTP (p. ej. smtp.gmail.com). Sin él no se envían correos y la
                              verificación del correo queda desactivada.
    BIOYOLOGIC_SMTP_PORT      587 (STARTTLS, por defecto) o 465 (SSL)
    BIOYOLOGIC_SMTP_USER      usuario SMTP (en Gmail, la cuenta que envía)
    BIOYOLOGIC_SMTP_PASSWORD  contraseña SMTP (en Gmail, una "contraseña de aplicación", no la normal)
    BIOYOLOGIC_MAIL_FROM      remitente visible (por defecto, el usuario SMTP)
"""

from __future__ import annotations

import logging
import os
import smtplib
from email.message import EmailMessage

log = logging.getLogger("uvicorn")


def configured() -> bool:
    return bool(os.environ.get("BIOYOLOGIC_SMTP_HOST"))


def send(to: str, subject: str, text: str) -> None:
    """Envía un correo de texto. Los errores se registran en el log (se llama en segundo plano)."""
    host = os.environ.get("BIOYOLOGIC_SMTP_HOST", "")
    port = int(os.environ.get("BIOYOLOGIC_SMTP_PORT", "587"))
    user = os.environ.get("BIOYOLOGIC_SMTP_USER", "")
    password = os.environ.get("BIOYOLOGIC_SMTP_PASSWORD", "")
    msg = EmailMessage()
    msg["From"] = os.environ.get("BIOYOLOGIC_MAIL_FROM") or f"Bioyologic <{user}>"
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)
    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=20) as s:
                if user:
                    s.login(user, password)
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=20) as s:
                s.starttls()
                if user:
                    s.login(user, password)
                s.send_message(msg)
    except (OSError, smtplib.SMTPException) as e:
        log.error("No se pudo enviar el correo a %s: %s", to, e)


def code_email(code: str, purpose: str, minutes: int) -> tuple[str, str]:
    """(asunto, texto) del correo con un código de 6 dígitos."""
    if purpose == "verify":
        subject = f"{code} es tu código para verificar tu cuenta de Bioyologic"
        intro = "Escribe este código en la app para verificar tu correo y empezar a usar Bioyologic:"
    else:
        subject = f"{code} es tu código para cambiar la contraseña de Bioyologic"
        intro = "Alguien pidió cambiar la contraseña de tu cuenta de Bioyologic. Si fuiste tú, usa este código:"
    text = (f"Hola:\n\n{intro}\n\n    {code}\n\nVence en {minutes} minutos.\n\n"
            "Si no fuiste tú, ignora este correo: tu cuenta sigue igual.\n\n"
            "— Bioyologic · Conteo y caracterización de bacterias desde tu celular\n")
    return subject, text

"""Envio de notificações por e-mail para visitantes e anfitriões."""
from __future__ import annotations

import logging
import smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage

from flask import current_app

from ..extensions import db
from ..models import STATUS_ACTIVE, VisitorPass

log = logging.getLogger(__name__)


def send_email(to: str, subject: str, body: str) -> bool:
    cfg = current_app.config
    if not to:
        return False
    if not cfg.get("MAIL_SERVER"):
        log.info("[e-mail simulado] Para: %s | Assunto: %s\n%s", to, subject, body)
        return True

    msg = EmailMessage()
    msg["From"] = cfg["MAIL_SENDER"]
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(cfg["MAIL_SERVER"], cfg["MAIL_PORT"], timeout=15) as smtp:
            if cfg.get("MAIL_USE_TLS"):
                smtp.starttls()
            if cfg.get("MAIL_USERNAME"):
                smtp.login(cfg["MAIL_USERNAME"], cfg["MAIL_PASSWORD"])
            smtp.send_message(msg)
        return True
    except (smtplib.SMTPException, OSError):
        log.exception("Falha ao enviar e-mail para %s", to)
        return False


def _visit_summary(p: VisitorPass) -> str:
    return (
        f"Visitante: {p.visitor_name}\n"
        f"Anfitrião: {p.host_name}\n"
        f"Entrada: {p.visit_start:%d/%m/%Y %H:%M}\n"
        f"Saída: {p.visit_end:%d/%m/%Y %H:%M}\n"
        f"Código: {p.short_code}\n"
    )


def notify_pass_created(p: VisitorPass, save_url: str | None) -> bool:
    company = current_app.config["COMPANY_NAME"]
    if save_url:
        wallet_line = f"Adicione seu cartão de visitante ao Google Wallet:\n{save_url}\n"
    else:
        wallet_line = (
            "Apresente o código abaixo na recepção.\n"
            f"Verificação: {current_app.config['BASE_URL']}/verificar/{p.token}\n"
        )
    body = (
        f"Olá, {p.visitor_name}!\n\n"
        f"Sua visita à {company} foi registrada.\n\n"
        f"{_visit_summary(p)}\n{wallet_line}"
    )
    return send_email(p.visitor_email, f"Seu cartão de visitante - {company}", body)


def send_due_reminders(now: datetime | None = None) -> int:
    """Envia lembretes para visitas que começam dentro da janela configurada.

    Pensado para ser executado periodicamente (cron, Cloud Scheduler) via
    `flask send-reminders`.
    """
    now = now or datetime.now()
    limit = now + timedelta(hours=current_app.config["REMINDER_HOURS_BEFORE"])
    due = (
        VisitorPass.query.filter(
            VisitorPass.status == STATUS_ACTIVE,
            VisitorPass.reminder_sent_at.is_(None),
            VisitorPass.visit_start > now,
            VisitorPass.visit_start <= limit,
        )
        .order_by(VisitorPass.visit_start)
        .all()
    )
    company = current_app.config["COMPANY_NAME"]
    sent = 0
    for p in due:
        summary = _visit_summary(p)
        send_email(
            p.visitor_email,
            f"Lembrete: sua visita à {company}",
            f"Olá, {p.visitor_name}!\n\nLembrete da sua visita:\n\n{summary}",
        )
        if p.host_email:
            send_email(
                p.host_email,
                f"Lembrete: você receberá {p.visitor_name}",
                f"Olá, {p.host_name}!\n\nVocê tem uma visita agendada:\n\n{summary}",
            )
        p.reminder_sent_at = now
        sent += 1
    db.session.commit()
    return sent

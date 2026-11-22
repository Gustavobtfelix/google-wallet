"""Comandos de linha de comando: `flask init-db`, `flask create-admin`, `flask send-reminders`."""
import time

import click
from flask import current_app
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError

from .extensions import db
from .models import User
from .services.notifications import send_due_reminders


def _ensure_sqlserver_database(uri: str) -> None:
    """No SQL Server o banco precisa existir antes de criar as tabelas."""
    url = make_url(uri)
    if not url.drivername.startswith("mssql") or not url.database:
        return
    literal = url.database.replace("'", "''")
    ident = url.database.replace("]", "]]")
    master = create_engine(url.set(database="master"), isolation_level="AUTOCOMMIT")
    with master.connect() as conn:
        conn.execute(text(f"IF DB_ID(N'{literal}') IS NULL CREATE DATABASE [{ident}]"))
    master.dispose()


@click.command("init-db")
@click.option("--retries", default=10, help="Tentativas de conexão (útil ao subir com Docker).")
def init_db(retries):
    """Cria o banco (SQL Server) e as tabelas."""
    uri = current_app.config["SQLALCHEMY_DATABASE_URI"]
    for attempt in range(1, retries + 1):
        try:
            _ensure_sqlserver_database(uri)
            db.create_all()
            click.echo("Banco de dados pronto.")
            return
        except OperationalError as exc:
            if attempt == retries:
                raise
            click.echo(f"Banco indisponível ({attempt}/{retries}), tentando novamente... {exc.orig}")
            time.sleep(3)


@click.command("create-admin")
@click.option("--name", prompt="Nome")
@click.option("--email", prompt="E-mail")
@click.option("--password", prompt="Senha", hide_input=True, confirmation_prompt=True)
def create_admin(name, email, password):
    """Cria (ou atualiza a senha de) um usuário da recepção."""
    email = email.strip().lower()
    user = User.query.filter_by(email=email).first()
    if user is None:
        user = User(name=name, email=email)
        db.session.add(user)
    user.set_password(password)
    db.session.commit()
    click.echo(f"Usuário {email} pronto.")


@click.command("send-reminders")
def send_reminders():
    """Envia lembretes das visitas próximas (agendar via cron / Cloud Scheduler)."""
    count = send_due_reminders()
    click.echo(f"{count} lembrete(s) enviado(s).")


def register(app):
    for cmd in (init_db, create_admin, send_reminders):
        app.cli.add_command(cmd)

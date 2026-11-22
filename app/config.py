"""Configurações da aplicação, lidas de variáveis de ambiente (arquivo .env)."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _bool(name: str, default: str = "false") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "sim"}


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-troque-em-producao")

    # Banco de dados: SQL Server em produção; SQLite como padrão para desenvolvimento local.
    # Exemplo SQL Server:
    # mssql+pyodbc://sa:SENHA@localhost:1433/visitantes?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{BASE_DIR / 'instance' / 'visitantes.db'}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    COMPANY_NAME = os.environ.get("COMPANY_NAME", "Minha Empresa")
    BASE_URL = os.environ.get("BASE_URL", "http://localhost:5000").rstrip("/")
    TIMEZONE = os.environ.get("TIMEZONE", "America/Sao_Paulo")

    # Google Wallet
    WALLET_ISSUER_ID = os.environ.get("WALLET_ISSUER_ID", "")
    WALLET_CLASS_SUFFIX = os.environ.get("WALLET_CLASS_SUFFIX", "cartao_visitante")
    GOOGLE_APPLICATION_CREDENTIALS = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
    WALLET_LOGO_URL = os.environ.get("WALLET_LOGO_URL", "")
    WALLET_BG_COLOR = os.environ.get("WALLET_BG_COLOR", "#1a73e8")

    # E-mail (notificações). Sem MAIL_SERVER, as mensagens são apenas registradas no log.
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", "587"))
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "")
    MAIL_USE_TLS = _bool("MAIL_USE_TLS", "true")
    MAIL_SENDER = os.environ.get("MAIL_SENDER", "nao-responda@exemplo.com")

    REMINDER_HOURS_BEFORE = int(os.environ.get("REMINDER_HOURS_BEFORE", "24"))


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
    WALLET_ISSUER_ID = ""
    GOOGLE_APPLICATION_CREDENTIALS = ""
    MAIL_SERVER = ""
    BASE_URL = "http://localhost"

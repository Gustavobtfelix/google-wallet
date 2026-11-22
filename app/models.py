"""Modelos de dados: usuários (recepção/administração) e cartões de visitante."""
import secrets
from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db, login_manager

STATUS_ACTIVE = "ativo"
STATUS_REVOKED = "revogado"


class User(UserMixin, db.Model):
    __tablename__ = "usuarios"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)

    passes = db.relationship("VisitorPass", back_populates="created_by", lazy="dynamic")

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


@login_manager.user_loader
def load_user(user_id: str):
    return db.session.get(User, int(user_id))


def _new_token() -> str:
    return secrets.token_hex(16)


class VisitorPass(db.Model):
    __tablename__ = "cartoes_visitante"

    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(32), unique=True, nullable=False, index=True, default=_new_token)

    visitor_name = db.Column(db.String(120), nullable=False)
    visitor_email = db.Column(db.String(255), nullable=False)
    visitor_document = db.Column(db.String(30))
    company = db.Column(db.String(120))

    host_name = db.Column(db.String(120), nullable=False)
    host_email = db.Column(db.String(255))

    visit_start = db.Column(db.DateTime, nullable=False, index=True)
    visit_end = db.Column(db.DateTime, nullable=False)
    purpose = db.Column(db.String(255))

    status = db.Column(db.String(20), nullable=False, default=STATUS_ACTIVE)
    wallet_object_id = db.Column(db.String(255))
    reminder_sent_at = db.Column(db.DateTime)

    created_by_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))
    created_by = db.relationship("User", back_populates="passes")
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)

    @property
    def short_code(self) -> str:
        return self.token[:8].upper()

    def validity(self, now: datetime | None = None) -> str:
        """Situação do cartão no momento: 'revogado', 'agendado', 'valido' ou 'expirado'."""
        now = now or datetime.now()
        if self.status == STATUS_REVOKED:
            return "revogado"
        if now < self.visit_start:
            return "agendado"
        if now > self.visit_end:
            return "expirado"
        return "valido"

    def is_valid(self, now: datetime | None = None) -> bool:
        return self.validity(now) == "valido"

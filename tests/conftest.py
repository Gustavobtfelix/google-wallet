from datetime import datetime, timedelta

import pytest

from app import create_app
from app.config import TestConfig
from app.extensions import db
from app.models import User, VisitorPass


@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        user = User(name="Recepção", email="recepcao@exemplo.com")
        user.set_password("senha123")
        db.session.add(user)
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def logged_client(client):
    client.post("/login", data={"email": "recepcao@exemplo.com", "password": "senha123"})
    return client


@pytest.fixture
def make_pass(app):
    def _make(**overrides):
        now = datetime.now().replace(second=0, microsecond=0)
        data = dict(
            visitor_name="Maria Souza",
            visitor_email="maria@exemplo.com",
            company="ACME",
            host_name="João Lima",
            host_email="joao@exemplo.com",
            visit_start=now - timedelta(hours=1),
            visit_end=now + timedelta(hours=2),
            purpose="Reunião",
        )
        data.update(overrides)
        p = VisitorPass(**data)
        db.session.add(p)
        db.session.commit()
        return p

    return _make

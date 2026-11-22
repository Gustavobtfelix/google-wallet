from datetime import datetime, timedelta

from app.extensions import db
from app.models import VisitorPass
from app.services.notifications import send_due_reminders


def test_requires_login(client):
    resp = client.get("/")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_login_invalid(client):
    resp = client.post("/login", data={"email": "recepcao@exemplo.com", "password": "errada"})
    assert "inválidos" in resp.get_data(as_text=True)


def test_create_pass(logged_client):
    resp = logged_client.post(
        "/cartoes/novo",
        data={
            "visitor_name": "Ana Paula",
            "visitor_email": "ANA@exemplo.com",
            "company": "Contoso",
            "host_name": "Carlos",
            "visit_start": "2030-01-10T09:00",
            "visit_end": "2030-01-10T11:00",
            "purpose": "Entrevista",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Ana Paula" in html
    assert "Modo demonstração" in html
    p = VisitorPass.query.one()
    assert p.visitor_email == "ana@exemplo.com"
    assert p.validity() == "agendado"


def test_create_pass_rejects_end_before_start(logged_client):
    resp = logged_client.post(
        "/cartoes/novo",
        data={
            "visitor_name": "Ana",
            "visitor_email": "ana@exemplo.com",
            "host_name": "Carlos",
            "visit_start": "2030-01-10T11:00",
            "visit_end": "2030-01-10T09:00",
        },
    )
    assert "posterior à entrada" in resp.get_data(as_text=True)
    assert VisitorPass.query.count() == 0


def test_list_search_and_filter(logged_client, make_pass):
    make_pass(visitor_name="Maria Souza")
    make_pass(visitor_name="Pedro Alves", company="Globex", status="revogado")
    html = logged_client.get("/?q=globex").get_data(as_text=True)
    assert "Pedro Alves" in html and "Maria Souza" not in html
    html = logged_client.get("/?situacao=valido").get_data(as_text=True)
    assert "Maria Souza" in html and "Pedro Alves" not in html


def test_edit_revoke_reactivate_delete(logged_client, make_pass):
    p = make_pass()
    resp = logged_client.post(
        f"/cartoes/{p.id}/editar",
        data={
            "visitor_name": "Maria S. Souza",
            "visitor_email": "maria@exemplo.com",
            "host_name": "João Lima",
            "visit_start": "2030-02-01T08:00",
            "visit_end": "2030-02-01T09:00",
        },
    )
    assert resp.status_code == 302
    assert db.session.get(VisitorPass, p.id).visitor_name == "Maria S. Souza"

    logged_client.post(f"/cartoes/{p.id}/revogar")
    assert db.session.get(VisitorPass, p.id).validity() == "revogado"
    logged_client.post(f"/cartoes/{p.id}/reativar")
    assert db.session.get(VisitorPass, p.id).status == "ativo"

    logged_client.post(f"/cartoes/{p.id}/excluir")
    assert db.session.get(VisitorPass, p.id) is None


def test_qrcode_svg(logged_client, make_pass):
    p = make_pass()
    resp = logged_client.get(f"/cartoes/{p.id}/qrcode.svg")
    assert resp.status_code == 200
    assert resp.mimetype == "image/svg+xml"


def test_public_verification(client, make_pass):
    valid = make_pass()
    expired = make_pass(
        visit_start=datetime.now() - timedelta(days=2),
        visit_end=datetime.now() - timedelta(days=1),
    )
    assert "Acesso liberado" in client.get(f"/verificar/{valid.token}").get_data(as_text=True)
    assert "expirado" in client.get(f"/verificar/{expired.token}").get_data(as_text=True)
    assert "não encontrado" in client.get("/verificar/xyz").get_data(as_text=True)

    data = client.get(f"/api/verificar/{valid.token}").get_json()
    assert data["valido"] is True
    assert client.get("/api/verificar/xyz").status_code == 404


def test_reminders_sent_once(app, make_pass):
    now = datetime.now()
    soon = make_pass(visit_start=now + timedelta(hours=3), visit_end=now + timedelta(hours=4))
    make_pass(visit_start=now + timedelta(days=5), visit_end=now + timedelta(days=5, hours=1))
    assert send_due_reminders(now) == 1
    assert db.session.get(VisitorPass, soon.id).reminder_sent_at is not None
    assert send_due_reminders(now) == 0

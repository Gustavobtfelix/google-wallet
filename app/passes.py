"""Rotas de gestão dos cartões de visitante (área autenticada) e verificação pública."""
import io
import json
import logging

import qrcode
import qrcode.image.svg
from flask import Blueprint, Response, abort, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_

from .extensions import db
from .forms import VisitorPassForm
from .models import STATUS_ACTIVE, STATUS_REVOKED, VisitorPass
from .services.notifications import notify_pass_created
from .services.wallet import WalletError, WalletService

log = logging.getLogger(__name__)

bp = Blueprint("passes", __name__)
public_bp = Blueprint("public", __name__)

FORM_FIELDS = (
    "visitor_name", "visitor_email", "visitor_document", "company",
    "host_name", "host_email", "visit_start", "visit_end", "purpose",
)


def _get_pass_or_404(pass_id: int) -> VisitorPass:
    p = db.session.get(VisitorPass, pass_id)
    if p is None:
        abort(404)
    return p


def _fill(p: VisitorPass, form: VisitorPassForm) -> None:
    for name in FORM_FIELDS:
        value = getattr(form, name).data
        if isinstance(value, str):
            value = value.strip() or None
        setattr(p, name, value)
    p.visitor_email = p.visitor_email.lower()
    if p.host_email:
        p.host_email = p.host_email.lower()


def _sync_wallet(p: VisitorPass) -> None:
    service = WalletService.from_app()
    if not service.enabled or not p.wallet_object_id:
        return
    try:
        if service.sync_object(p):
            flash("Cartão atualizado também no Google Wallet do visitante.", "info")
    except WalletError as exc:
        flash(f"Não foi possível atualizar o Google Wallet: {exc}", "warning")


# ---------------------------------------------------------------- área autenticada
@bp.route("/")
@login_required
def index():
    q = request.args.get("q", "").strip()
    situacao = request.args.get("situacao", "")
    query = VisitorPass.query
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(
                VisitorPass.visitor_name.ilike(like),
                VisitorPass.company.ilike(like),
                VisitorPass.host_name.ilike(like),
                VisitorPass.visitor_email.ilike(like),
            )
        )
    passes = query.order_by(VisitorPass.visit_start.desc()).all()
    if situacao:
        passes = [p for p in passes if p.validity() == situacao]
    return render_template("passes/list.html", passes=passes, q=q, situacao=situacao)


@bp.route("/cartoes/novo", methods=["GET", "POST"])
@login_required
def create():
    form = VisitorPassForm()
    if form.validate_on_submit():
        p = VisitorPass(created_by=current_user)
        _fill(p, form)
        db.session.add(p)
        db.session.flush()  # gera o id/token antes de montar o cartão

        service = WalletService.from_app()
        save_url = None
        if service.enabled:
            try:
                save_url = service.save_url(p)
                p.wallet_object_id = service.object_id(p)
            except WalletError as exc:
                flash(f"Cartão criado, mas houve erro no Google Wallet: {exc}", "warning")
        db.session.commit()

        if notify_pass_created(p, save_url):
            flash(f"Cartão criado e enviado para {p.visitor_email}.", "success")
        else:
            flash("Cartão criado, mas o e-mail não pôde ser enviado.", "warning")
        return redirect(url_for("passes.detail", pass_id=p.id))
    return render_template("passes/form.html", form=form, title="Novo cartão de visitante")


@bp.route("/cartoes/<int:pass_id>")
@login_required
def detail(pass_id):
    p = _get_pass_or_404(pass_id)
    service = WalletService.from_app()
    save_url = None
    if service.enabled and p.status == STATUS_ACTIVE:
        try:
            save_url = service.save_url(p)
        except WalletError as exc:
            flash(str(exc), "warning")
    wallet_json = json.dumps(service.build_object(p), indent=2, ensure_ascii=False)
    return render_template(
        "passes/detail.html",
        p=p,
        save_url=save_url,
        wallet_enabled=service.enabled,
        wallet_json=wallet_json,
        verify_url=service.verify_url(p),
    )


@bp.route("/cartoes/<int:pass_id>/editar", methods=["GET", "POST"])
@login_required
def edit(pass_id):
    p = _get_pass_or_404(pass_id)
    form = VisitorPassForm(obj=p)
    if form.validate_on_submit():
        _fill(p, form)
        p.reminder_sent_at = None  # novo horário => novo lembrete
        db.session.commit()
        _sync_wallet(p)
        flash("Cartão atualizado.", "success")
        return redirect(url_for("passes.detail", pass_id=p.id))
    return render_template("passes/form.html", form=form, title="Editar cartão", p=p)


@bp.route("/cartoes/<int:pass_id>/revogar", methods=["POST"])
@login_required
def revoke(pass_id):
    p = _get_pass_or_404(pass_id)
    p.status = STATUS_REVOKED
    db.session.commit()
    _sync_wallet(p)
    flash("Cartão revogado. Ele não dará mais acesso.", "success")
    return redirect(url_for("passes.detail", pass_id=p.id))


@bp.route("/cartoes/<int:pass_id>/reativar", methods=["POST"])
@login_required
def reactivate(pass_id):
    p = _get_pass_or_404(pass_id)
    p.status = STATUS_ACTIVE
    db.session.commit()
    _sync_wallet(p)
    flash("Cartão reativado.", "success")
    return redirect(url_for("passes.detail", pass_id=p.id))


@bp.route("/cartoes/<int:pass_id>/reenviar", methods=["POST"])
@login_required
def resend(pass_id):
    p = _get_pass_or_404(pass_id)
    service = WalletService.from_app()
    save_url = service.save_url(p) if service.enabled and p.status == STATUS_ACTIVE else None
    if notify_pass_created(p, save_url):
        flash(f"E-mail reenviado para {p.visitor_email}.", "success")
    else:
        flash("Falha ao reenviar o e-mail.", "danger")
    return redirect(url_for("passes.detail", pass_id=p.id))


@bp.route("/cartoes/<int:pass_id>/excluir", methods=["POST"])
@login_required
def delete(pass_id):
    p = _get_pass_or_404(pass_id)
    if p.status == STATUS_ACTIVE:
        p.status = STATUS_REVOKED
        _sync_wallet(p)  # expira o cartão na carteira antes de apagar o registro
    db.session.delete(p)
    db.session.commit()
    flash("Cartão excluído.", "success")
    return redirect(url_for("passes.index"))


@bp.route("/cartoes/<int:pass_id>/qrcode.svg")
@login_required
def qr_svg(pass_id):
    p = _get_pass_or_404(pass_id)
    img = qrcode.make(
        WalletService.from_app().verify_url(p),
        image_factory=qrcode.image.svg.SvgPathImage,
        box_size=8,
    )
    buf = io.BytesIO()
    img.save(buf)
    return Response(buf.getvalue(), mimetype="image/svg+xml")


# ---------------------------------------------------------------- verificação pública (portaria)
@public_bp.route("/verificar/<token>")
def verify(token):
    p = VisitorPass.query.filter_by(token=token).first()
    situacao = p.validity() if p else "inexistente"
    return render_template("verify.html", p=p, situacao=situacao)


@public_bp.route("/api/verificar/<token>")
def verify_api(token):
    """Endpoint JSON para integração com catracas/leitores de QR Code."""
    p = VisitorPass.query.filter_by(token=token).first()
    if p is None:
        return jsonify({"valido": False, "situacao": "inexistente"}), 404
    return jsonify(
        {
            "valido": p.is_valid(),
            "situacao": p.validity(),
            "visitante": p.visitor_name,
            "anfitriao": p.host_name,
            "entrada": p.visit_start.isoformat(),
            "saida": p.visit_end.isoformat(),
        }
    )


@public_bp.route("/saude")
def health():
    return {"status": "ok", "empresa": current_app.config["COMPANY_NAME"]}

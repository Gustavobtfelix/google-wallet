"""Sistema de criação automatizada de cartões de visitante com Google Wallet."""
import logging
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from flask import Flask, render_template  # noqa: E402

from . import commands  # noqa: E402
from .config import Config  # noqa: E402
from .extensions import csrf, db, login_manager  # noqa: E402


def create_app(config_class=Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_class)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    uri = app.config["SQLALCHEMY_DATABASE_URI"]
    if uri.startswith("sqlite:///"):
        Path(uri.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    from .auth import bp as auth_bp
    from .passes import bp as passes_bp
    from .passes import public_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(passes_bp)
    app.register_blueprint(public_bp)
    csrf.exempt(public_bp)

    commands.register(app)

    @app.context_processor
    def inject_globals():
        return {"company_name": app.config["COMPANY_NAME"]}

    @app.errorhandler(404)
    def not_found(_):
        return render_template("404.html"), 404

    return app

"""Application Factory.

Struktur nach dem Flask Mega-Tutorial (M. Grinberg), Kapitel 15
"A Better Application Structure": Erweiterungen werden global erzeugt und in
create_app() an die konkrete App gebunden; Funktionsbereiche sind Blueprints.
"""
from flask import Flask
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect
from sqlalchemy import MetaData
from werkzeug.middleware.proxy_fix import ProxyFix

from config import Config

# Einheitliche Namen für Constraints, damit Alembic-Migrationen auf
# PostgreSQL und SQLite gleich funktionieren.
naming_convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

db = SQLAlchemy(metadata=MetaData(naming_convention=naming_convention))
migrate = Migrate()
login = LoginManager()
login.login_view = "auth.login"
login.login_message = "Bitte melde dich an, um diese Seite zu sehen."
csrf = CSRFProtect()


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    # Umlaute im JSON des API lesbar ausgeben (statt \u00e4)
    app.json.ensure_ascii = False

    db.init_app(app)
    migrate.init_app(app, db, render_as_batch=True)
    login.init_app(app)
    csrf.init_app(app)

    # Erweiterung gegenüber dem Unterricht: Hinter Nginx (und Cloudflare Tunnel)
    # sieht Flask sonst nur 127.0.0.1 und "http". ProxyFix übernimmt die von
    # Nginx gesetzten X-Forwarded-* Header.
    # Quelle: https://flask.palletsprojects.com/en/latest/deploying/proxy_fix/
    if app.config["PROXY_COUNT"]:
        n = app.config["PROXY_COUNT"]
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=n, x_proto=n, x_host=n)

    from app.errors import bp as errors_bp
    app.register_blueprint(errors_bp)

    from app.auth import bp as auth_bp
    app.register_blueprint(auth_bp, url_prefix="/auth")

    from app.main import bp as main_bp
    app.register_blueprint(main_bp)

    from app.api import bp as api_bp
    app.register_blueprint(api_bp, url_prefix="/api")
    # Die API nutzt Token statt Session-Cookies -> kein CSRF-Schutz nötig.
    csrf.exempt(api_bp)

    from app import cli
    cli.register(app)

    from app.models import STATUS_LABELS

    @app.context_processor
    def inject_labels():
        return {"STATUS_LABELS": STATUS_LABELS}

    return app


from app import models  # noqa: E402,F401

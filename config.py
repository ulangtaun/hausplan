"""Konfiguration der Anwendung.

Aufbau nach dem Muster aus dem Unterricht (Flask Mega-Tutorial, Kap. 4):
Alle Werte werden aus Umgebungsvariablen gelesen (Datei .env), damit
Passwörter und Schlüssel nicht im Git-Repository landen.
"""
import os

from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, ".env"))


def _bool(name, default=False):
    return os.environ.get(name, str(default)).lower() in ("1", "true", "yes", "on")


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or "dev-nur-lokal-aendern"

    # Produktiv: postgresql+psycopg2://hausplan:<pw>@<db-host>/hausplan
    # Lokal ohne PostgreSQL funktioniert die App auch mit SQLite.
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or (
        "sqlite:///" + os.path.join(basedir, "hausplan.db")
    )
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    # Hinter Cloudflare läuft die Seite immer über HTTPS -> Cookies nur über HTTPS senden.
    SESSION_COOKIE_SECURE = _bool("SESSION_COOKIE_SECURE", False)
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    # Anzahl Reverse-Proxies vor Gunicorn (Nginx = 1), siehe app/__init__.py (ProxyFix)
    PROXY_COUNT = int(os.environ.get("PROXY_COUNT", "0"))

    # Gültigkeit eines API-Tokens in Sekunden (Standard: 7 Tage)
    API_TOKEN_LIFETIME = int(os.environ.get("API_TOKEN_LIFETIME", str(7 * 24 * 3600)))


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    SQLALCHEMY_ENGINE_OPTIONS = {}
    WTF_CSRF_ENABLED = False
    SERVER_NAME = "localhost"

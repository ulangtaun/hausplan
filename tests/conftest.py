"""Gemeinsame Test-Fixtures. Jeder Test erhält eine frische In-Memory-SQLite-Datenbank."""
import base64

import pytest

from app import create_app, db
from app.models import ROLE_OWNER, Household, Project, User
from config import TestConfig


@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def make_user(name, password="geheim123"):
    u = User(username=name, email=f"{name}@example.com")
    u.set_password(password)
    db.session.add(u)
    return u


@pytest.fixture
def household(app):
    """Haushalt mit zwei Mitgliedern (anna = Besitzerin, ben) und Standard-Kriterien."""
    anna, ben = make_user("anna"), make_user("ben")
    h = Household(name="Testhaus", budget_chf=1000, hours_available=20)
    db.session.add(h)
    h.add_member(anna, role=ROLE_OWNER)
    h.add_member(ben)
    h.create_default_criteria()
    db.session.commit()
    return h


def user(name):
    return db.session.scalar(db.select(User).where(User.username == name))


def project(h, title, cost=0, hours=0, by="anna"):
    p = Project(household=h, title=title, estimated_cost=cost, estimated_hours=hours, created_by=user(by))
    db.session.add(p)
    db.session.flush()
    return p


def rate_all(p, values_anna, values_ben):
    """Bewertet ein Projekt durch anna und ben (Werte in Kriterien-Reihenfolge)."""
    from app.services.ratings import save_ratings
    crit = list(p.household.criteria)
    save_ratings(p, user("anna"), {c.id: v for c, v in zip(crit, values_anna)})
    save_ratings(p, user("ben"), {c.id: v for c, v in zip(crit, values_ben)})


def basic(username, password="geheim123"):
    raw = f"{username}:{password}".encode()
    return {"Authorization": "Basic " + base64.b64encode(raw).decode()}


def bearer(token):
    return {"Authorization": f"Bearer {token}"}

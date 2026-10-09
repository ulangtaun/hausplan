"""Tests der Weboberfläche und des REST-API (T01, T02, T11, T12 im Testprotokoll)."""
from app import db
from app.models import Household, User
from tests.conftest import basic, bearer, make_user, project, rate_all


def login(client, username, password="geheim123"):
    return client.post("/auth/login", data={"username": username, "password": password},
                       follow_redirects=True)


# --- T01 Registrierung ---------------------------------------------------------
def test_T01_register_and_unique_username_email(client, app):
    data = {"username": "nury", "email": "nury@example.com", "password": "sicher123",
            "password2": "sicher123"}
    r = client.post("/auth/register", data=data, follow_redirects=True)
    assert "Registrierung erfolgreich" in r.text
    assert db.session.scalar(db.select(User).where(User.username == "nury")) is not None

    # gleicher Benutzername (andere Gross-/Kleinschreibung) und gleiche E-Mail
    r = client.post("/auth/register", data=dict(data, username="Nury"))
    assert "bereits vergeben" in r.text
    r = client.post("/auth/register", data=dict(data, username="anderer"))
    assert "bereits registriert" in r.text


def test_T01_password_rules(client):
    r = client.post("/auth/register", data={"username": "kurz", "email": "k@example.com",
                                            "password": "123", "password2": "123"})
    assert "Mindestens 8 Zeichen" in r.text


# --- T02 Login / Zugriffsschutz --------------------------------------------------
def test_T02_login_required_and_wrong_password(client, household):
    r = client.get(f"/households/{household.id}")
    assert r.status_code == 302 and "/auth/login" in r.headers["Location"]
    r = login(client, "anna", "falsch")
    assert "falsch" in r.text
    r = login(client, "anna")
    assert "Testhaus" in r.text


def test_web_full_flow(client, household):
    """Idee erfassen, bewerten, Status wechseln über die Weboberfläche."""
    login(client, "anna")
    r = client.post(f"/households/{household.id}/projects/new",
                    data={"title": "Balkon streichen", "estimated_cost": "80", "estimated_hours": "4"},
                    follow_redirects=True)
    assert "Idee erfasst" in r.text
    p = household.projects[-1]
    form = {f"c_{c.id}": "4" for c in household.criteria}
    r = client.post(f"/projects/{p.id}/rate", data=form, follow_redirects=True)
    assert "Bewertung gespeichert" in r.text
    # ben fehlt -> Einplanen nicht möglich (idee -> geplant ist kein erlaubter Übergang)
    r = client.post(f"/projects/{p.id}/status", data={"target": "geplant"}, follow_redirects=True)
    assert "nicht vorgesehen" in r.text


def test_web_other_household_forbidden(client, household):
    make_user("fremd")
    db.session.commit()
    login(client, "fremd")
    assert client.get(f"/households/{household.id}").status_code == 403


# --- T11 API: Authentifizierung ohne Browser und Daten lesen --------------------
def test_T11_api_token_and_read(client, household):
    p = project(household, "Lampe", cost=120, hours=2)
    rate_all(p, [5, 4, 3, 2], [3, 3, 3, 3])
    db.session.commit()

    assert client.get("/api/households").status_code == 401             # ohne Token
    assert client.post("/api/tokens", headers=basic("anna", "falsch")).status_code == 401

    r = client.post("/api/tokens", headers=basic("anna"))
    assert r.status_code == 200
    token = r.get_json()["token"]

    r = client.get(f"/api/households/{household.id}/projects", headers=bearer(token))
    assert r.status_code == 200
    items = r.get_json()["items"]
    assert items[0]["title"] == "Lampe" and items[0]["score"] == 65.6

    for path in ("ranking", "order", "plan", "stats"):
        assert client.get(f"/api/households/{household.id}/{path}", headers=bearer(token)).status_code == 200
    r = client.get(f"/api/projects/{p.id}", headers=bearer(token))
    assert r.get_json()["rating"]["all_members_rated"] is True

    # Token widerrufen -> danach ungültig
    assert client.delete("/api/tokens", headers=bearer(token)).status_code == 204
    assert client.get("/api/households", headers=bearer(token)).status_code == 401


def test_api_status_filter_and_create(client, household):
    token = client.post("/api/tokens", headers=basic("ben")).get_json()["token"]
    r = client.post(f"/api/households/{household.id}/projects", headers=bearer(token),
                    json={"title": "Pflanzen umtopfen", "estimated_cost": 30, "estimated_hours": 1})
    assert r.status_code == 201 and r.get_json()["status"] == "idee"
    r = client.post(f"/api/households/{household.id}/projects", headers=bearer(token),
                    json={"estimated_cost": -5})
    assert r.status_code == 400
    r = client.get(f"/api/households/{household.id}/projects?status=idee", headers=bearer(token))
    assert r.get_json()["count"] == 1
    r = client.get(f"/api/households/{household.id}/projects?status=quatsch", headers=bearer(token))
    assert r.status_code == 400


# --- T12 API: Berechtigung -------------------------------------------------------
def test_T12_api_foreign_household_forbidden(client, household):
    make_user("fremd")
    other = Household(name="Geheim")
    db.session.add(other)
    db.session.commit()
    token = client.post("/api/tokens", headers=basic("fremd")).get_json()["token"]
    r = client.get(f"/api/households/{household.id}/projects", headers=bearer(token))
    assert r.status_code == 403 and r.is_json
    p = project(household, "Privat")
    db.session.commit()
    assert client.get(f"/api/projects/{p.id}", headers=bearer(token)).status_code == 403
    assert client.get("/api/projects/9999", headers=bearer(token)).status_code == 404

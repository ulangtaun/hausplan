"""Eigene Flask-CLI-Befehle (Mega-Tutorial Kap. 13: app.cli).

    flask seed --password <pw>    legt Demo-Benutzer und Beispieldaten an
    flask create-user             legt einen Benutzer interaktiv an
"""
import click
import sqlalchemy as sa

from app import db
from app.models import ROLE_OWNER, Household, Project, User
from app.services.dependencies import add_dependency
from app.services.ratings import save_ratings
from app.services.workflow import change_status

# (Titel, Beschreibung, Kosten, Stunden, Bewertungen examinator, Bewertungen mitbewohner)
# Bewertungen in der Reihenfolge der Standard-Kriterien: Nutzen, Dringlichkeit, Freude, Aufwand
DEMO_PROJECTS = [
    ("Wohnzimmerwand streichen", "Altweiss statt Vergilbt. Abdeckmaterial ist schon im Keller.",
     300, 8, [4, 4, 3, 2], [4, 3, 3, 2]),
    ("Neue Wohnzimmerlampe montieren", "Die Hängelampe vom Brocki aufhängen, braucht neuen Baldachin.",
     250, 3, [3, 2, 4, 1], [4, 2, 3, 1]),
    ("Hochbeet auf dem Balkon", "Lärchenholz, ca. 120 x 60 cm, für Kräuter und Salat.",
     180, 6, [5, 2, 5, 3], [2, 1, 2, 4]),
    ("Heizungssteuerung smart machen", "Thermostatköpfe mit Zigbee, Steuerung über Home Assistant (Proxmox).",
     450, 10, [4, 4, 5, 3], [3, 4, 2, 3]),
    ("Keller entrümpeln", "Alles, was seit 2 Jahren nicht gebraucht wurde, verkaufen oder entsorgen.",
     0, 12, [4, 3, 1, 3], [5, 4, 1, 3]),
    ("Badezimmer neu plätteln", "Offerte vom Plattenleger einholen.",
     4000, 40, [4, 2, 2, 5], [4, 3, 2, 5]),
    ("Velo-Abstellplatz im Keller", "Wandhalterungen für drei Velos – erst wenn der Keller leer ist.",
     600, 14, [4, 3, 3, 3], None),
    ("Fenster im Schlafzimmer abdichten", "Neue Dichtungen, es zieht im Winter.",
     120, 4, [4, 5, 1, 2], [4, 5, 1, 2]),
    ("Sauna im Garten", "Schöne Idee, aber zu teuer und keine Bewilligung.",
     8000, 60, [3, 1, 5, 5], [2, 1, 4, 5]),
]


def register(app):

    @app.cli.command("seed")
    @click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True,
                  help="Passwort für alle Demo-Benutzer")
    @click.option("--reset", is_flag=True, help="Vorhandene Demo-Daten zuerst löschen")
    def seed(password, reset):
        """Demo-Benutzer 'examinator' und 'mitbewohner' mit Beispieldaten anlegen."""
        names = ["examinator", "mitbewohner"]
        existing = db.session.scalars(sa.select(User).where(User.username.in_(names))).all()
        if existing and not reset:
            raise click.ClickException("Demo-Benutzer existieren bereits. Mit --reset neu anlegen.")
        if reset:
            for u in existing:
                for h in u.households():
                    if h.name in ("Demo-Wohnung", "WG des Bruders"):
                        db.session.delete(h)
                db.session.delete(u)
            db.session.commit()

        ex = User(username="examinator", email="examinator@example.com")
        mb = User(username="mitbewohner", email="mitbewohner@example.com")
        for u in (ex, mb):
            u.set_password(password)
            db.session.add(u)

        h = Household(name="Demo-Wohnung", budget_chf=2500, hours_available=60)
        db.session.add(h)
        h.add_member(ex, role=ROLE_OWNER)
        h.add_member(mb)
        h.create_default_criteria()

        # Zweiter Haushalt, auf den 'examinator' KEINEN Zugriff hat (Berechtigungstest)
        other = Household(name="WG des Bruders", budget_chf=500, hours_available=20)
        db.session.add(other)
        other.add_member(mb, role=ROLE_OWNER)
        other.create_default_criteria()
        db.session.flush()
        db.session.add(Project(household=other, created_by=mb, title="Gamingecke einrichten",
                               estimated_cost=350, estimated_hours=5))

        projects = {}
        criteria = list(h.criteria)
        for title, desc, cost, hours, r_ex, r_mb in DEMO_PROJECTS:
            p = Project(household=h, created_by=ex, title=title, description=desc,
                        estimated_cost=cost, estimated_hours=hours)
            db.session.add(p)
            db.session.flush()
            save_ratings(p, ex, {c.id: v for c, v in zip(criteria, r_ex)})
            if r_mb:
                save_ratings(p, mb, {c.id: v for c, v in zip(criteria, r_mb)})
            projects[title] = p

        P = projects
        add_dependency(P["Neue Wohnzimmerlampe montieren"], P["Wohnzimmerwand streichen"])
        add_dependency(P["Velo-Abstellplatz im Keller"], P["Keller entrümpeln"])

        # Abgeschlossene Projekte (liefern Daten für die Schätzgenauigkeit)
        for title, cost, hrs in (("Wohnzimmerwand streichen", 380, 11),
                                 ("Fenster im Schlafzimmer abdichten", 105, 5)):
            p = P[title]
            change_status(p, "geplant")
            change_status(p, "in_arbeit")
            change_status(p, "erledigt", actual_cost=cost, actual_hours=hrs)

        change_status(P["Neue Wohnzimmerlampe montieren"], "geplant")
        change_status(P["Heizungssteuerung smart machen"], "geplant")
        change_status(P["Heizungssteuerung smart machen"], "in_arbeit")
        change_status(P["Sauna im Garten"], "verworfen")

        db.session.commit()
        click.echo("Demo-Daten angelegt: Benutzer 'examinator' (Besitzer) und 'mitbewohner'.")

    @app.cli.command("create-user")
    @click.argument("username")
    @click.argument("email")
    @click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True)
    def create_user(username, email, password):
        """Benutzer anlegen (Alternative zur Registrierung im Browser)."""
        if db.session.scalar(sa.select(User).where(sa.or_(User.username == username, User.email == email))):
            raise click.ClickException("Benutzername oder E-Mail existiert bereits.")
        u = User(username=username, email=email)
        u.set_password(password)
        db.session.add(u)
        db.session.commit()
        click.echo(f"Benutzer {username} angelegt.")

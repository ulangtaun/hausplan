"""Datenmodell von HausPlan.

Schreibweise mit SQLAlchemy 2.x (Mapped / mapped_column) wie in der aktuellen
Fassung des Flask Mega-Tutorials (Kap. 4).

Tabellen:
    user                 Benutzerkonten
    household            Haushalt (Gruppe), z. B. "Wohnung Bern"
    membership           n:m User <-> Household, mit Rolle (Assoziationsobjekt)
    criterion            Bewertungskriterien eines Haushalts mit Gewicht
    project              Projekt / Idee eines Haushalts
    rating               Bewertung: User x Projekt x Kriterium -> Wert 1..5
    project_dependency   n:m Selbstbeziehung Projekt -> Projekt (Abhängigkeit)
"""
import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

import sqlalchemy as sa
import sqlalchemy.orm as so
from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app import db, login


def utcnow():
    return datetime.now(timezone.utc)


def _aware(dt):
    """SQLite liefert Zeitstempel ohne Zeitzone zurück -> als UTC interpretieren."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


# --------------------------------------------------------------------------
# Status-Workflow eines Projekts (Regeln siehe app/services/workflow.py)
# --------------------------------------------------------------------------
STATUS_IDEE = "idee"
STATUS_BEWERTET = "bewertet"
STATUS_GEPLANT = "geplant"
STATUS_IN_ARBEIT = "in_arbeit"
STATUS_ERLEDIGT = "erledigt"
STATUS_VERWORFEN = "verworfen"

STATUS_ORDER = [STATUS_IDEE, STATUS_BEWERTET, STATUS_GEPLANT,
                STATUS_IN_ARBEIT, STATUS_ERLEDIGT, STATUS_VERWORFEN]
STATUS_LABELS = {
    STATUS_IDEE: "Idee",
    STATUS_BEWERTET: "Bewertet",
    STATUS_GEPLANT: "Geplant",
    STATUS_IN_ARBEIT: "In Arbeit",
    STATUS_ERLEDIGT: "Erledigt",
    STATUS_VERWORFEN: "Verworfen",
}
# Projekte in diesen Status gelten als "offen" (noch nicht abgeschlossen)
OPEN_STATUSES = {STATUS_IDEE, STATUS_BEWERTET, STATUS_GEPLANT, STATUS_IN_ARBEIT}

ROLE_OWNER = "owner"
ROLE_MEMBER = "member"

DIRECTION_BENEFIT = "benefit"   # hoher Wert = gut   (z. B. Nutzen)
DIRECTION_COST = "cost"         # hoher Wert = schlecht (z. B. Aufwand)

# Standard-Kriterien für neue Haushalte: (Name, Gewicht, Richtung, Beschreibung)
DEFAULT_CRITERIA = [
    ("Nutzen", 3, DIRECTION_BENEFIT, "Wie sehr verbessert das Projekt unseren Alltag?"),
    ("Dringlichkeit", 2, DIRECTION_BENEFIT, "Wie dringend muss es gemacht werden?"),
    ("Freude", 1, DIRECTION_BENEFIT, "Wie viel Spass macht uns das Projekt?"),
    ("Aufwand", 2, DIRECTION_COST, "Wie viel Zeit, Geld und Nerven kostet es? (5 = sehr viel)"),
]


# n:m Selbstbeziehung: project_id hängt ab von depends_on_id
project_dependency = sa.Table(
    "project_dependency",
    db.metadata,
    sa.Column("project_id", sa.ForeignKey("project.id", ondelete="CASCADE"), primary_key=True),
    sa.Column("depends_on_id", sa.ForeignKey("project.id", ondelete="CASCADE"), primary_key=True),
)


class User(UserMixin, db.Model):
    id: so.Mapped[int] = so.mapped_column(primary_key=True)
    username: so.Mapped[str] = so.mapped_column(sa.String(64), index=True, unique=True)
    email: so.Mapped[str] = so.mapped_column(sa.String(120), index=True, unique=True)
    password_hash: so.Mapped[Optional[str]] = so.mapped_column(sa.String(256))
    created_at: so.Mapped[datetime] = so.mapped_column(sa.DateTime(timezone=True), default=utcnow)

    # Token-Authentifizierung für das API (Mega-Tutorial Kap. 23)
    token: so.Mapped[Optional[str]] = so.mapped_column(sa.String(64), index=True, unique=True)
    token_expiration: so.Mapped[Optional[datetime]] = so.mapped_column(sa.DateTime(timezone=True))

    memberships: so.Mapped[list["Membership"]] = so.relationship(
        back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User {self.username}>"

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return self.password_hash is not None and check_password_hash(self.password_hash, password)

    # --- Haushalte -------------------------------------------------------
    def households(self):
        return db.session.scalars(
            sa.select(Household).join(Membership)
            .where(Membership.user_id == self.id)
            .order_by(Household.name)
        ).all()

    def membership_in(self, household):
        return db.session.scalar(
            sa.select(Membership).where(Membership.user_id == self.id,
                                        Membership.household_id == household.id))

    def is_member(self, household):
        return self.membership_in(household) is not None

    def is_owner(self, household):
        m = self.membership_in(household)
        return m is not None and m.role == ROLE_OWNER

    # --- API-Token -------------------------------------------------------
    def get_token(self, expires_in=7 * 24 * 3600):
        now = utcnow()
        if self.token and self.token_expiration and _aware(self.token_expiration) > now + timedelta(seconds=60):
            return self.token
        self.token = secrets.token_hex(32)
        self.token_expiration = now + timedelta(seconds=expires_in)
        db.session.add(self)
        return self.token

    def revoke_token(self):
        self.token_expiration = utcnow() - timedelta(seconds=1)

    @staticmethod
    def check_token(token):
        user = db.session.scalar(sa.select(User).where(User.token == token))
        if user is None or user.token_expiration is None or _aware(user.token_expiration) < utcnow():
            return None
        return user

    def to_dict(self, include_email=False):
        data = {"id": self.id, "username": self.username}
        if include_email:
            data["email"] = self.email
        return data


@login.user_loader
def load_user(id):
    return db.session.get(User, int(id))


class Household(db.Model):
    id: so.Mapped[int] = so.mapped_column(primary_key=True)
    name: so.Mapped[str] = so.mapped_column(sa.String(100))
    # Planungsrahmen pro Quartal (für den Budget-Vorschlag)
    budget_chf: so.Mapped[Decimal] = so.mapped_column(sa.Numeric(10, 2), default=Decimal("0"))
    hours_available: so.Mapped[Decimal] = so.mapped_column(sa.Numeric(7, 1), default=Decimal("0"))
    created_at: so.Mapped[datetime] = so.mapped_column(sa.DateTime(timezone=True), default=utcnow)

    memberships: so.Mapped[list["Membership"]] = so.relationship(
        back_populates="household", cascade="all, delete-orphan")
    criteria: so.Mapped[list["Criterion"]] = so.relationship(
        back_populates="household", cascade="all, delete-orphan", order_by="Criterion.id")
    projects: so.Mapped[list["Project"]] = so.relationship(
        back_populates="household", cascade="all, delete-orphan", order_by="Project.id")

    __table_args__ = (
        sa.CheckConstraint("budget_chf >= 0", name="budget_positive"),
        sa.CheckConstraint("hours_available >= 0", name="hours_positive"),
    )

    def __repr__(self):
        return f"<Household {self.name}>"

    @property
    def members(self):
        return [m.user for m in sorted(self.memberships, key=lambda m: m.user.username.lower())]

    def add_member(self, user, role=ROLE_MEMBER):
        m = Membership(user=user, household=self, role=role)
        db.session.add(m)
        return m

    def create_default_criteria(self):
        for name, weight, direction, description in DEFAULT_CRITERIA:
            db.session.add(Criterion(household=self, name=name, weight=weight,
                                     direction=direction, description=description))

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "budget_chf": float(self.budget_chf or 0),
            "hours_available": float(self.hours_available or 0),
            "members": [{"id": m.user.id, "username": m.user.username, "role": m.role}
                        for m in self.memberships],
            "criteria": [c.to_dict() for c in self.criteria],
        }


class Membership(db.Model):
    """Assoziationsobjekt für die n:m-Beziehung User <-> Household mit Zusatzattribut Rolle."""
    user_id: so.Mapped[int] = so.mapped_column(
        sa.ForeignKey("user.id", ondelete="CASCADE"), primary_key=True)
    household_id: so.Mapped[int] = so.mapped_column(
        sa.ForeignKey("household.id", ondelete="CASCADE"), primary_key=True)
    role: so.Mapped[str] = so.mapped_column(sa.String(10), default=ROLE_MEMBER)
    joined_at: so.Mapped[datetime] = so.mapped_column(sa.DateTime(timezone=True), default=utcnow)

    user: so.Mapped[User] = so.relationship(back_populates="memberships")
    household: so.Mapped[Household] = so.relationship(back_populates="memberships")

    __table_args__ = (sa.CheckConstraint("role IN ('owner', 'member')", name="role_valid"),)


class Criterion(db.Model):
    id: so.Mapped[int] = so.mapped_column(primary_key=True)
    household_id: so.Mapped[int] = so.mapped_column(
        sa.ForeignKey("household.id", ondelete="CASCADE"), index=True)
    name: so.Mapped[str] = so.mapped_column(sa.String(50))
    description: so.Mapped[Optional[str]] = so.mapped_column(sa.String(200))
    weight: so.Mapped[int] = so.mapped_column(default=1)
    direction: so.Mapped[str] = so.mapped_column(sa.String(10), default=DIRECTION_BENEFIT)

    household: so.Mapped[Household] = so.relationship(back_populates="criteria")
    ratings: so.Mapped[list["Rating"]] = so.relationship(
        back_populates="criterion", cascade="all, delete-orphan")

    __table_args__ = (
        sa.CheckConstraint("weight BETWEEN 1 AND 5", name="weight_range"),
        sa.CheckConstraint("direction IN ('benefit', 'cost')", name="direction_valid"),
        sa.UniqueConstraint("household_id", "name", name="uq_criterion_household_name"),
    )

    def to_dict(self):
        return {"id": self.id, "name": self.name, "weight": self.weight,
                "direction": self.direction, "description": self.description}


class Project(db.Model):
    id: so.Mapped[int] = so.mapped_column(primary_key=True)
    household_id: so.Mapped[int] = so.mapped_column(
        sa.ForeignKey("household.id", ondelete="CASCADE"), index=True)
    created_by_id: so.Mapped[Optional[int]] = so.mapped_column(
        sa.ForeignKey("user.id", ondelete="SET NULL"))
    title: so.Mapped[str] = so.mapped_column(sa.String(120))
    description: so.Mapped[Optional[str]] = so.mapped_column(sa.Text)
    status: so.Mapped[str] = so.mapped_column(sa.String(20), default=STATUS_IDEE, index=True)

    # Schätzung und Ist-Werte (Ist-Werte beim Abschluss)
    estimated_cost: so.Mapped[Decimal] = so.mapped_column(sa.Numeric(10, 2), default=Decimal("0"))
    estimated_hours: so.Mapped[Decimal] = so.mapped_column(sa.Numeric(7, 1), default=Decimal("0"))
    actual_cost: so.Mapped[Optional[Decimal]] = so.mapped_column(sa.Numeric(10, 2))
    actual_hours: so.Mapped[Optional[Decimal]] = so.mapped_column(sa.Numeric(7, 1))

    created_at: so.Mapped[datetime] = so.mapped_column(sa.DateTime(timezone=True), default=utcnow)
    started_at: so.Mapped[Optional[datetime]] = so.mapped_column(sa.DateTime(timezone=True))
    completed_at: so.Mapped[Optional[datetime]] = so.mapped_column(sa.DateTime(timezone=True))

    household: so.Mapped[Household] = so.relationship(back_populates="projects")
    created_by: so.Mapped[Optional[User]] = so.relationship()
    ratings: so.Mapped[list["Rating"]] = so.relationship(
        back_populates="project", cascade="all, delete-orphan")

    # Selbstreferenzierende n:m-Beziehung (Muster "Followers", Mega-Tutorial Kap. 8)
    dependencies: so.Mapped[list["Project"]] = so.relationship(
        secondary=project_dependency,
        primaryjoin=(project_dependency.c.project_id == id),
        secondaryjoin=(project_dependency.c.depends_on_id == id),
        back_populates="dependents",
        order_by="Project.title",
    )
    dependents: so.Mapped[list["Project"]] = so.relationship(
        secondary=project_dependency,
        primaryjoin=(project_dependency.c.depends_on_id == id),
        secondaryjoin=(project_dependency.c.project_id == id),
        back_populates="dependencies",
        order_by="Project.title",
    )

    __table_args__ = (
        sa.CheckConstraint("estimated_cost >= 0", name="est_cost_positive"),
        sa.CheckConstraint("estimated_hours >= 0", name="est_hours_positive"),
        sa.CheckConstraint(
            "status IN ('idee','bewertet','geplant','in_arbeit','erledigt','verworfen')",
            name="status_valid"),
    )

    def __repr__(self):
        return f"<Project {self.title} [{self.status}]>"

    @property
    def status_label(self):
        return STATUS_LABELS.get(self.status, self.status)

    @property
    def is_open(self):
        return self.status in OPEN_STATUSES

    @property
    def open_dependencies(self):
        """Abhängigkeiten, die noch nicht erledigt sind (blockieren den Start)."""
        return [d for d in self.dependencies if d.status != STATUS_ERLEDIGT]


class Rating(db.Model):
    id: so.Mapped[int] = so.mapped_column(primary_key=True)
    project_id: so.Mapped[int] = so.mapped_column(
        sa.ForeignKey("project.id", ondelete="CASCADE"), index=True)
    user_id: so.Mapped[int] = so.mapped_column(
        sa.ForeignKey("user.id", ondelete="CASCADE"), index=True)
    criterion_id: so.Mapped[int] = so.mapped_column(
        sa.ForeignKey("criterion.id", ondelete="CASCADE"), index=True)
    value: so.Mapped[int] = so.mapped_column()
    updated_at: so.Mapped[datetime] = so.mapped_column(
        sa.DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    project: so.Mapped[Project] = so.relationship(back_populates="ratings")
    user: so.Mapped[User] = so.relationship()
    criterion: so.Mapped[Criterion] = so.relationship(back_populates="ratings")

    __table_args__ = (
        sa.CheckConstraint("value BETWEEN 1 AND 5", name="value_range"),
        sa.UniqueConstraint("project_id", "user_id", "criterion_id", name="uq_rating_once"),
    )

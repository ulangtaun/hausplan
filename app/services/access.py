"""Zugriffsregeln: Wer darf welchen Haushalt / welches Projekt sehen und ändern?

Regeln:
* Nur Mitglieder eines Haushalts sehen dessen Projekte (sonst 403).
* Nur Besitzer (owner) ändern Einstellungen, Kriterien und Mitglieder.
* Ein Projekt löschen darf, wer es erfasst hat, oder ein Besitzer.

Wird von Web-Oberfläche und API gemeinsam genutzt. Die Fehlerseiten in
app/errors.py liefern für /api/... automatisch JSON statt HTML.
"""
import sqlalchemy as sa
from flask import abort

from app import db
from app.models import ROLE_MEMBER, ROLE_OWNER, Household, Membership, Project


def household_for(user, household_id, owner_required=False):
    household = db.session.get(Household, household_id)
    if household is None:
        abort(404)
    m = user.membership_in(household)
    if m is None:
        abort(403)
    if owner_required and m.role != ROLE_OWNER:
        abort(403)
    return household


def project_for(user, project_id):
    project = db.session.get(Project, project_id)
    if project is None:
        abort(404)
    if not user.is_member(project.household):
        abort(403)
    return project


def can_delete_project(user, project):
    return project.created_by_id == user.id or user.is_owner(project.household)


class MembershipError(Exception):
    pass


def owner_count(household):
    return db.session.scalar(
        sa.select(sa.func.count()).select_from(Membership)
        .where(Membership.household_id == household.id, Membership.role == ROLE_OWNER))


def remove_member(household, user):
    """Entfernt ein Mitglied. Der letzte Besitzer kann nicht entfernt werden."""
    m = user.membership_in(household)
    if m is None:
        raise MembershipError("Diese Person ist kein Mitglied.")
    if m.role == ROLE_OWNER and owner_count(household) <= 1:
        raise MembershipError("Der letzte Besitzer kann nicht entfernt werden.")
    # Bewertungen der Person in diesem Haushalt entfernen, damit Scores stimmen
    for p in household.projects:
        for r in [r for r in p.ratings if r.user_id == user.id]:
            db.session.delete(r)
    db.session.delete(m)


def set_role(household, user, role):
    m = user.membership_in(household)
    if m is None:
        raise MembershipError("Diese Person ist kein Mitglied.")
    if role not in (ROLE_OWNER, ROLE_MEMBER):
        raise MembershipError("Ungültige Rolle.")
    if m.role == ROLE_OWNER and role == ROLE_MEMBER and owner_count(household) <= 1:
        raise MembershipError("Es muss mindestens einen Besitzer geben.")
    m.role = role

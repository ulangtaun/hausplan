"""Speichern einer Bewertung inkl. Validierung und automatischem Statuswechsel."""
from app import db
from app.models import Rating
from app.services.scoring import validate_value
from app.services.workflow import RATABLE_STATUSES, after_rating_changed


class RatingError(Exception):
    pass


def save_ratings(project, user, values):
    """Speichert die Bewertungen eines Benutzers für ein Projekt.

    values: {criterion_id: wert 1..5}; es müssen ALLE Kriterien des Haushalts
            bewertet werden (Teilbewertungen würden den Score verfälschen).
    Rückgabe: True, wenn das Projekt dadurch automatisch auf "bewertet" wechselte.
    """
    if project.status not in RATABLE_STATUSES:
        raise RatingError(f"Projekte im Status «{project.status_label}» können nicht mehr bewertet werden.")
    if not user.is_member(project.household):
        raise RatingError("Nur Haushaltsmitglieder können bewerten.")

    criteria = {c.id: c for c in project.household.criteria}
    if not criteria:
        raise RatingError("Der Haushalt hat noch keine Bewertungskriterien.")
    try:
        cleaned = {int(k): validate_value(v) for k, v in values.items()}
    except ValueError as e:
        raise RatingError(str(e))
    unknown = set(cleaned) - set(criteria)
    if unknown:
        raise RatingError("Unbekanntes Kriterium.")
    missing = [criteria[c].name for c in criteria if c not in cleaned]
    if missing:
        raise RatingError("Bitte alle Kriterien bewerten (fehlt: " + ", ".join(missing) + ").")

    existing = {r.criterion_id: r for r in project.ratings if r.user_id == user.id}
    for cid, value in cleaned.items():
        if cid in existing:
            existing[cid].value = value
        else:
            r = Rating(project=project, user=user, criterion=criteria[cid], value=value)
            db.session.add(r)
    db.session.flush()
    return after_rating_changed(project)

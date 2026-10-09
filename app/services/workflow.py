"""Geschäftslogik 2: Status-Workflow eines Projekts (Zustandsautomat).

    idee ──(alle bewertet, automatisch)──> bewertet ──> geplant ──> in_arbeit ──> erledigt
      ^                                       ^           │  ^          │
      │                                       └───────────┘  └──────────┘
      └──── verworfen <──── (aus jedem offenen Status)        (zurückstellen / pausieren)

Regeln (Guards):
* bewertet -> geplant     nur wenn ALLE Haushaltsmitglieder vollständig bewertet haben
* geplant  -> in_arbeit   nur wenn alle Abhängigkeiten erledigt sind
* in_arbeit -> erledigt   nur mit Ist-Kosten und Ist-Stunden (für die Schätzgenauigkeit)
* -> verworfen            nicht, solange ein offenes Projekt davon abhängt
* verworfen -> idee       Reaktivieren (Bewertungen bleiben erhalten)

Der Übergang idee -> bewertet passiert automatisch, sobald alle Mitglieder
vollständig bewertet haben (siehe after_rating_changed()).
"""
from decimal import Decimal, InvalidOperation

from app.models import (
    OPEN_STATUSES, STATUS_BEWERTET, STATUS_ERLEDIGT, STATUS_GEPLANT, STATUS_IDEE,
    STATUS_IN_ARBEIT, STATUS_LABELS, STATUS_VERWORFEN, utcnow,
)
from app.services.scoring import compute_project_score


class WorkflowError(Exception):
    """Ein Statuswechsel ist nicht erlaubt. Die Meldung ist für Benutzer gedacht."""


# Erlaubte Übergänge: von -> {nach}
TRANSITIONS = {
    STATUS_IDEE: {STATUS_VERWORFEN},
    STATUS_BEWERTET: {STATUS_GEPLANT, STATUS_VERWORFEN},
    STATUS_GEPLANT: {STATUS_IN_ARBEIT, STATUS_BEWERTET, STATUS_VERWORFEN},
    STATUS_IN_ARBEIT: {STATUS_ERLEDIGT, STATUS_GEPLANT, STATUS_VERWORFEN},
    STATUS_ERLEDIGT: set(),
    STATUS_VERWORFEN: {STATUS_IDEE},
}

# Beschriftung der Aktions-Buttons in der Weboberfläche
ACTION_LABELS = {
    (STATUS_BEWERTET, STATUS_GEPLANT): "Einplanen",
    (STATUS_GEPLANT, STATUS_IN_ARBEIT): "Starten",
    (STATUS_GEPLANT, STATUS_BEWERTET): "Zurückstellen",
    (STATUS_IN_ARBEIT, STATUS_ERLEDIGT): "Abschliessen",
    (STATUS_IN_ARBEIT, STATUS_GEPLANT): "Pausieren",
    (STATUS_VERWORFEN, STATUS_IDEE): "Reaktivieren",
}

# In diesen Status darf noch bewertet werden
RATABLE_STATUSES = {STATUS_IDEE, STATUS_BEWERTET, STATUS_GEPLANT}


def check_transition(project, target):
    """Liefert eine Liste von Gründen, warum der Wechsel nicht geht (leer = erlaubt)."""
    reasons = []
    if target not in STATUS_LABELS:
        return [f"Unbekannter Status «{target}»."]
    if target not in TRANSITIONS.get(project.status, set()):
        return [f"Wechsel von «{STATUS_LABELS[project.status]}» nach "
                f"«{STATUS_LABELS[target]}» ist nicht vorgesehen."]

    if target == STATUS_GEPLANT and project.status == STATUS_BEWERTET:
        score = compute_project_score(project)
        if not score.all_rated:
            names = ", ".join(u.username for u in score.missing_raters)
            reasons.append(f"Noch nicht alle haben bewertet (fehlt: {names}).")

    if target == STATUS_IN_ARBEIT:
        open_deps = project.open_dependencies
        if open_deps:
            names = ", ".join(f"«{d.title}»" for d in open_deps)
            reasons.append(f"Blockiert durch offene Abhängigkeiten: {names}.")

    if target == STATUS_VERWORFEN:
        active = [d for d in project.dependents if d.status in OPEN_STATUSES]
        if active:
            names = ", ".join(f"«{d.title}»" for d in active)
            reasons.append(f"Andere offene Projekte hängen davon ab: {names}.")
    return reasons


def allowed_actions(project):
    """Alle Folgestatus mit Beschriftung und ggf. Sperrgrund (für die UI)."""
    actions = []
    for target in sorted(TRANSITIONS.get(project.status, set()),
                         key=lambda s: list(STATUS_LABELS).index(s)):
        if target == STATUS_VERWORFEN:
            label = "Verwerfen"
        else:
            label = ACTION_LABELS.get((project.status, target), STATUS_LABELS[target])
        actions.append({"target": target, "label": label,
                        "blocked_by": check_transition(project, target)})
    return actions


def _parse_amount(value, name):
    try:
        d = Decimal(str(value).replace(",", ".").replace("'", ""))
    except (InvalidOperation, ValueError):
        raise WorkflowError(f"{name} ist keine gültige Zahl.")
    if d < 0:
        raise WorkflowError(f"{name} darf nicht negativ sein.")
    return d


def change_status(project, target, actual_cost=None, actual_hours=None):
    """Führt einen Statuswechsel aus oder wirft WorkflowError.

    Die Änderung wird nur an den Objekten vorgenommen, das Speichern
    (db.session.commit) erfolgt im Aufrufer.
    """
    reasons = check_transition(project, target)
    if reasons:
        raise WorkflowError(" ".join(reasons))

    if target == STATUS_ERLEDIGT:
        if actual_cost in (None, "") or actual_hours in (None, ""):
            raise WorkflowError("Zum Abschliessen bitte Ist-Kosten und Ist-Stunden angeben.")
        project.actual_cost = _parse_amount(actual_cost, "Ist-Kosten")
        project.actual_hours = _parse_amount(actual_hours, "Ist-Stunden")
        project.completed_at = utcnow()

    if target == STATUS_IN_ARBEIT and project.started_at is None:
        project.started_at = utcnow()

    project.status = target
    return project


def after_rating_changed(project):
    """Automatischer Übergang idee -> bewertet, sobald alle vollständig bewertet haben.

    Gibt True zurück, wenn der Status geändert wurde.
    """
    if project.status == STATUS_IDEE and compute_project_score(project).all_rated:
        project.status = STATUS_BEWERTET
        return True
    return False

"""API-Endpunkte für Haushalte (lesend) und das Erfassen neuer Ideen (schreibend)."""
from decimal import Decimal, InvalidOperation

from flask import request, url_for

from app import db
from app.api import bp
from app.api.auth import token_auth
from app.api.errors import bad_request
from app.api.serializers import project_to_dict
from app.models import STATUS_LABELS, Project
from app.services.access import household_for
from app.services.dependencies import suggested_order
from app.services.planning import budget_proposal, estimation_accuracy, proposal_to_api
from app.services.scoring import rank_projects


@bp.route("/households", methods=["GET"])
@token_auth.login_required
def list_households():
    user = token_auth.current_user()
    return {"items": [
        {"id": h.id, "name": h.name, "projects": len(h.projects),
         "_links": {"self": url_for("api.get_household", id=h.id)}}
        for h in user.households()]}


@bp.route("/households/<int:id>", methods=["GET"])
@token_auth.login_required
def get_household(id):
    h = household_for(token_auth.current_user(), id)
    data = h.to_dict()
    data["_links"] = {
        "projects": url_for("api.household_projects", id=id),
        "ranking": url_for("api.household_ranking", id=id),
        "order": url_for("api.household_order", id=id),
        "plan": url_for("api.household_plan", id=id),
        "stats": url_for("api.household_stats", id=id),
    }
    return data


@bp.route("/households/<int:id>/projects", methods=["GET"])
@token_auth.login_required
def household_projects(id):
    """Alle Projekte, optional gefiltert: ?status=geplant"""
    h = household_for(token_auth.current_user(), id)
    status = request.args.get("status")
    if status and status not in STATUS_LABELS:
        return bad_request(f"Unbekannter Status. Erlaubt: {', '.join(STATUS_LABELS)}")
    projects = [p for p in h.projects if not status or p.status == status]
    return {"items": [project_to_dict(p) for p in projects], "count": len(projects)}


@bp.route("/households/<int:id>/projects", methods=["POST"])
@token_auth.login_required
def create_project(id):
    """Neue Idee erfassen (z. B. per iOS-Kurzbefehl).

    JSON: {"title": "...", "description": "...", "estimated_cost": 120, "estimated_hours": 4}
    """
    user = token_auth.current_user()
    h = household_for(user, id)
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    if not title:
        return bad_request("Feld 'title' ist erforderlich.")
    if len(title) > 120:
        return bad_request("Titel darf höchstens 120 Zeichen lang sein.")
    values = {}
    for field in ("estimated_cost", "estimated_hours"):
        try:
            values[field] = Decimal(str(data.get(field, 0)))
        except (InvalidOperation, ValueError):
            return bad_request(f"Feld '{field}' muss eine Zahl sein.")
        if values[field] < 0:
            return bad_request(f"Feld '{field}' darf nicht negativ sein.")
    p = Project(household=h, created_by=user, title=title,
                description=data.get("description") or None, **values)
    db.session.add(p)
    db.session.commit()
    return project_to_dict(p, detail=True), 201, {"Location": url_for("api.get_project", id=p.id)}


@bp.route("/households/<int:id>/ranking", methods=["GET"])
@token_auth.login_required
def household_ranking(id):
    """Offene Projekte nach Nutzwert-Score sortiert."""
    h = household_for(token_auth.current_user(), id)
    ranked = rank_projects([p for p in h.projects if p.is_open])
    return {"items": [dict(project_to_dict(p, s), rank=i + 1)
                      for i, (p, s) in enumerate(ranked)]}


@bp.route("/households/<int:id>/order", methods=["GET"])
@token_auth.login_required
def household_order(id):
    """Empfohlene Reihenfolge (topologische Sortierung nach Abhängigkeiten)."""
    h = household_for(token_auth.current_user(), id)
    order, leftovers = suggested_order(h.projects)
    return {
        "items": [{"step": o["step"], "id": o["project"].id, "title": o["project"].title,
                   "status": o["project"].status,
                   "score": None if o["score"] is None else round(o["score"], 1),
                   "after": [d.title for d in o["waits_for"]]} for o in order],
        "unsortable": [p.title for p in leftovers],
    }


@bp.route("/households/<int:id>/plan", methods=["GET"])
@token_auth.login_required
def household_plan(id):
    """Budget-Vorschlag "Was liegt drin?" für das Quartal."""
    h = household_for(token_auth.current_user(), id)
    return proposal_to_api(budget_proposal(h))


@bp.route("/households/<int:id>/stats", methods=["GET"])
@token_auth.login_required
def household_stats(id):
    """Kennzahlen: Projekte pro Status und Schätzgenauigkeit."""
    h = household_for(token_auth.current_user(), id)
    counts = {s: 0 for s in STATUS_LABELS}
    for p in h.projects:
        counts[p.status] += 1
    return {"projects_by_status": counts, "estimation": estimation_accuracy(h)}

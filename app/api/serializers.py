"""Umwandlung von Modellen in JSON-taugliche Dictionaries."""
from flask import url_for

from app.services.scoring import compute_project_score


def _f(v):
    return None if v is None else float(v)


def project_to_dict(p, score=None, detail=False):
    score = score or compute_project_score(p)
    data = {
        "id": p.id,
        "household_id": p.household_id,
        "title": p.title,
        "status": p.status,
        "status_label": p.status_label,
        "score": None if score.score is None else round(score.score, 1),
        "disagreement": score.disagreement,
        "estimated_cost": _f(p.estimated_cost),
        "estimated_hours": _f(p.estimated_hours),
        "blocked": bool(p.open_dependencies),
        "_links": {"self": url_for("api.get_project", id=p.id)},
    }
    if detail:
        members = {u.id: u.username for u in p.household.members}
        data.update({
            "description": p.description,
            "actual_cost": _f(p.actual_cost),
            "actual_hours": _f(p.actual_hours),
            "created_by": p.created_by.username if p.created_by else None,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "started_at": p.started_at.isoformat() if p.started_at else None,
            "completed_at": p.completed_at.isoformat() if p.completed_at else None,
            "rating": {
                "user_scores": {members.get(uid, str(uid)): round(s, 1)
                                for uid, s in score.user_scores.items()},
                "missing_raters": [u.username for u in score.missing_raters],
                "all_members_rated": score.all_rated,
                "disagreement_reasons": score.disagreement_reasons,
            },
            "depends_on": [{"id": d.id, "title": d.title, "status": d.status} for d in p.dependencies],
            "required_by": [{"id": d.id, "title": d.title, "status": d.status} for d in p.dependents],
        })
    return data

from app.api import bp
from app.api.auth import token_auth
from app.api.serializers import project_to_dict
from app.services.access import project_for


@bp.route("/projects/<int:id>", methods=["GET"])
@token_auth.login_required
def get_project(id):
    """Projekt mit Bewertungen, Konsens und Abhängigkeiten."""
    p = project_for(token_auth.current_user(), id)
    return project_to_dict(p, detail=True)

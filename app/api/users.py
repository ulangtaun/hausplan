from app.api import bp
from app.api.auth import token_auth


@bp.route("/users/me", methods=["GET"])
@token_auth.login_required
def me():
    user = token_auth.current_user()
    data = user.to_dict(include_email=True)
    data["households"] = [{"id": h.id, "name": h.name} for h in user.households()]
    return data

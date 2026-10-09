from flask import current_app

from app import db
from app.api import bp
from app.api.auth import basic_auth, token_auth


@bp.route("/tokens", methods=["POST"])
@basic_auth.login_required
def get_token():
    """Token holen:  http --auth user:pw POST https://host/api/tokens"""
    token = basic_auth.current_user().get_token(current_app.config["API_TOKEN_LIFETIME"])
    user = basic_auth.current_user()
    db.session.commit()
    return {"token": token, "expires": user.token_expiration.isoformat()}


@bp.route("/tokens", methods=["DELETE"])
@token_auth.login_required
def revoke_token():
    token_auth.current_user().revoke_token()
    db.session.commit()
    return "", 204

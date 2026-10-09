"""Fehlerbehandlung für Web (HTML) und API (JSON).

Nach Mega-Tutorial Kap. 23: Anfragen an /api/... erhalten JSON-Fehler,
alle anderen eine HTML-Fehlerseite.
"""
from flask import Blueprint, render_template, request

from app import db
from app.api.errors import error_response

bp = Blueprint("errors", __name__)


def wants_json():
    return request.path.startswith("/api/")


@bp.app_errorhandler(403)
def forbidden(error):
    if wants_json():
        return error_response(403, "Kein Zugriff auf diese Ressource.")
    return render_template("errors/error.html", code=403,
                           message="Du hast keinen Zugriff auf diese Seite."), 403


@bp.app_errorhandler(404)
def not_found(error):
    if wants_json():
        return error_response(404)
    return render_template("errors/error.html", code=404,
                           message="Diese Seite gibt es nicht."), 404


@bp.app_errorhandler(405)
def method_not_allowed(error):
    if wants_json():
        return error_response(405)
    return render_template("errors/error.html", code=405,
                           message="Diese Aktion ist hier nicht erlaubt."), 405


@bp.app_errorhandler(500)
def internal_error(error):
    db.session.rollback()
    if wants_json():
        return error_response(500)
    return render_template("errors/error.html", code=500,
                           message="Ein unerwarteter Fehler ist aufgetreten."), 500

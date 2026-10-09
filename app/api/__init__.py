from flask import Blueprint

bp = Blueprint("api", __name__)

from app.api import tokens, users, households, projects  # noqa: E402,F401

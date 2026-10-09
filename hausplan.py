"""Einstiegspunkt für Flask-CLI und Gunicorn (gunicorn hausplan:app)."""
import sqlalchemy as sa
import sqlalchemy.orm as so

from app import create_app, db
from app.models import Criterion, Household, Membership, Project, Rating, User

app = create_app()


@app.shell_context_processor
def make_shell_context():
    return {"sa": sa, "so": so, "db": db, "User": User, "Household": Household,
            "Membership": Membership, "Criterion": Criterion, "Project": Project, "Rating": Rating}

from flask_wtf import FlaskForm
from wtforms import DecimalField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, Optional

from app.models import DIRECTION_BENEFIT, DIRECTION_COST


class EmptyForm(FlaskForm):
    """Nur für CSRF-Schutz bei Buttons (z. B. Löschen)."""
    submit = SubmitField("OK")


class HouseholdForm(FlaskForm):
    name = StringField("Name des Haushalts", validators=[DataRequired(), Length(max=100)])
    budget_chf = DecimalField("Budget pro Quartal (CHF)", places=2, default=0,
                              validators=[Optional(), NumberRange(min=0, message="Darf nicht negativ sein.")])
    hours_available = DecimalField("Verfügbare Stunden pro Quartal", places=1, default=0,
                                   validators=[Optional(), NumberRange(min=0, message="Darf nicht negativ sein.")])
    submit = SubmitField("Speichern")


class CriterionForm(FlaskForm):
    name = StringField("Kriterium", validators=[DataRequired(), Length(max=50)])
    description = StringField("Hilfetext", validators=[Optional(), Length(max=200)])
    weight = SelectField("Gewicht", coerce=int, choices=[(i, str(i)) for i in range(1, 6)], default=2)
    direction = SelectField("Richtung", choices=[
        (DIRECTION_BENEFIT, "Je höher, desto besser (z. B. Nutzen)"),
        (DIRECTION_COST, "Je höher, desto schlechter (z. B. Aufwand)")])
    submit = SubmitField("Kriterium hinzufügen")


class AddMemberForm(FlaskForm):
    username = StringField("Benutzername", validators=[DataRequired(), Length(max=64)])
    submit = SubmitField("Hinzufügen")


class ProjectForm(FlaskForm):
    title = StringField("Titel", validators=[DataRequired(), Length(max=120)])
    description = TextAreaField("Beschreibung", validators=[Optional(), Length(max=5000)])
    estimated_cost = DecimalField("Geschätzte Kosten (CHF)", places=2, default=0,
                                  validators=[Optional(), NumberRange(min=0, message="Darf nicht negativ sein.")])
    estimated_hours = DecimalField("Geschätzter Aufwand (Stunden)", places=1, default=0,
                                   validators=[Optional(), NumberRange(min=0, message="Darf nicht negativ sein.")])
    submit = SubmitField("Speichern")

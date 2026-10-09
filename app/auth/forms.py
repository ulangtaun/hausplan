import sqlalchemy as sa
from flask_wtf import FlaskForm
from wtforms import BooleanField, PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo, Length, Regexp, ValidationError

from app import db
from app.models import User


class LoginForm(FlaskForm):
    username = StringField("Benutzername", validators=[DataRequired()])
    password = PasswordField("Passwort", validators=[DataRequired()])
    remember_me = BooleanField("Angemeldet bleiben")
    submit = SubmitField("Anmelden")


class RegistrationForm(FlaskForm):
    username = StringField("Benutzername", validators=[
        DataRequired(), Length(min=3, max=64),
        Regexp(r"^[A-Za-z0-9_.-]+$", message="Nur Buchstaben, Zahlen, Punkt, _ und -.")])
    email = StringField("E-Mail", validators=[DataRequired(), Email(), Length(max=120)])
    password = PasswordField("Passwort", validators=[DataRequired(), Length(min=8, message="Mindestens 8 Zeichen.")])
    password2 = PasswordField("Passwort wiederholen", validators=[
        DataRequired(), EqualTo("password", message="Passwörter stimmen nicht überein.")])
    submit = SubmitField("Registrieren")

    # Eindeutigkeit von Benutzername und E-Mail (Anforderung 2.1.1)
    def validate_username(self, username):
        user = db.session.scalar(sa.select(User).where(
            sa.func.lower(User.username) == username.data.lower()))
        if user is not None:
            raise ValidationError("Dieser Benutzername ist bereits vergeben.")

    def validate_email(self, email):
        user = db.session.scalar(sa.select(User).where(
            sa.func.lower(User.email) == email.data.lower()))
        if user is not None:
            raise ValidationError("Diese E-Mail-Adresse ist bereits registriert.")

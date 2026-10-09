"""Routen der Weboberfläche.

Die Routen sind bewusst schlank: Validierung und Regeln liegen in
app/services/, damit Web und API dieselbe Logik verwenden.
"""
from decimal import Decimal

import sqlalchemy as sa
from flask import abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.main import bp
from app.main.forms import AddMemberForm, CriterionForm, EmptyForm, HouseholdForm, ProjectForm
from app.models import (
    ROLE_MEMBER, ROLE_OWNER, STATUS_ERLEDIGT, STATUS_ORDER, Criterion, Household, Project, User,
)
from app.services.access import (
    MembershipError, can_delete_project, household_for, project_for, remove_member, set_role,
)
from app.services.dependencies import DependencyError, add_dependency, remove_dependency, suggested_order
from app.services.planning import budget_proposal, estimation_accuracy
from app.services.ratings import RatingError, save_ratings
from app.services.scoring import compute_project_score, rank_projects
from app.services.workflow import RATABLE_STATUSES, WorkflowError, allowed_actions, change_status


def _dec(value):
    return Decimal(value) if value is not None else Decimal("0")


# ---------------------------------------------------------------------------
# Start / Haushalte
# ---------------------------------------------------------------------------
@bp.route("/")
@login_required
def index():
    households = current_user.households()
    overview = []
    for h in households:
        counts = {s: 0 for s in STATUS_ORDER}
        for p in h.projects:
            counts[p.status] += 1
        overview.append((h, counts))
    form = HouseholdForm()
    return render_template("main/index.html", title="Meine Haushalte", overview=overview, form=form)


@bp.route("/households/new", methods=["POST"])
@login_required
def create_household():
    form = HouseholdForm()
    if form.validate_on_submit():
        h = Household(name=form.name.data.strip(), budget_chf=_dec(form.budget_chf.data),
                      hours_available=_dec(form.hours_available.data))
        db.session.add(h)
        h.add_member(current_user, role=ROLE_OWNER)
        h.create_default_criteria()
        db.session.commit()
        flash(f"Haushalt «{h.name}» erstellt – mit vier Standard-Kriterien zur Bewertung.", "success")
        return redirect(url_for("main.household", id=h.id))
    for errors in form.errors.values():
        for e in errors:
            flash(e, "danger")
    return redirect(url_for("main.index"))


@bp.route("/households/<int:id>")
@login_required
def household(id):
    h = household_for(current_user, id)
    show_closed = request.args.get("closed") == "1"
    columns = {s: [] for s in STATUS_ORDER}
    for p, score in rank_projects(h.projects):
        columns[p.status].append((p, score))
    plan = budget_proposal(h)
    return render_template("main/household.html", title=h.name, household=h, columns=columns,
                           show_closed=show_closed, plan=plan,
                           is_owner=current_user.is_owner(h))


@bp.route("/households/<int:id>/settings", methods=["GET", "POST"])
@login_required
def household_settings(id):
    h = household_for(current_user, id, owner_required=True)
    form = HouseholdForm(obj=h if request.method == "GET" else None)
    if form.validate_on_submit():
        h.name = form.name.data.strip()
        h.budget_chf = _dec(form.budget_chf.data)
        h.hours_available = _dec(form.hours_available.data)
        db.session.commit()
        flash("Einstellungen gespeichert.", "success")
        return redirect(url_for("main.household_settings", id=id))
    return render_template("main/settings.html", title="Einstellungen", household=h, form=form,
                           criterion_form=CriterionForm(), member_form=AddMemberForm(),
                           empty_form=EmptyForm())


@bp.route("/households/<int:id>/criteria", methods=["POST"])
@login_required
def add_criterion(id):
    h = household_for(current_user, id, owner_required=True)
    form = CriterionForm()
    if form.validate_on_submit():
        name = form.name.data.strip()
        if any(c.name.lower() == name.lower() for c in h.criteria):
            flash(f"Ein Kriterium «{name}» gibt es bereits.", "danger")
        else:
            db.session.add(Criterion(household=h, name=name, description=form.description.data or None,
                                     weight=form.weight.data, direction=form.direction.data))
            db.session.commit()
            flash(f"Kriterium «{name}» hinzugefügt. Bestehende Projekte müssen dafür neu bewertet werden.",
                  "warning")
    else:
        for errors in form.errors.values():
            for e in errors:
                flash(e, "danger")
    return redirect(url_for("main.household_settings", id=id))


@bp.route("/criteria/<int:cid>/weight", methods=["POST"])
@login_required
def update_criterion_weight(cid):
    c = db.session.get(Criterion, cid) or abort(404)
    household_for(current_user, c.household_id, owner_required=True)
    try:
        weight = int(request.form.get("weight", ""))
    except ValueError:
        weight = 0
    if not 1 <= weight <= 5:
        flash("Gewicht muss zwischen 1 und 5 liegen.", "danger")
    else:
        c.weight = weight
        db.session.commit()
        flash(f"Gewicht von «{c.name}» auf {weight} gesetzt – alle Scores wurden neu berechnet.", "success")
    return redirect(url_for("main.household_settings", id=c.household_id))


@bp.route("/criteria/<int:cid>/delete", methods=["POST"])
@login_required
def delete_criterion(cid):
    c = db.session.get(Criterion, cid) or abort(404)
    h = household_for(current_user, c.household_id, owner_required=True)
    if len(h.criteria) <= 1:
        flash("Mindestens ein Kriterium muss bestehen bleiben.", "danger")
    elif EmptyForm().validate_on_submit():
        name = c.name
        db.session.delete(c)
        db.session.commit()
        flash(f"Kriterium «{name}» und alle zugehörigen Bewertungen gelöscht.", "info")
    return redirect(url_for("main.household_settings", id=h.id))


@bp.route("/households/<int:id>/members", methods=["POST"])
@login_required
def add_member(id):
    h = household_for(current_user, id, owner_required=True)
    form = AddMemberForm()
    if form.validate_on_submit():
        user = db.session.scalar(sa.select(User).where(User.username == form.username.data.strip()))
        if user is None:
            flash("Kein Benutzer mit diesem Namen gefunden. Die Person muss sich zuerst registrieren.", "danger")
        elif user.is_member(h):
            flash(f"{user.username} ist bereits Mitglied.", "info")
        else:
            h.add_member(user)
            db.session.commit()
            flash(f"{user.username} wurde hinzugefügt.", "success")
    return redirect(url_for("main.household_settings", id=id))


@bp.route("/households/<int:id>/members/<int:uid>/<action>", methods=["POST"])
@login_required
def member_action(id, uid, action):
    h = household_for(current_user, id, owner_required=True)
    user = db.session.get(User, uid) or abort(404)
    if not EmptyForm().validate_on_submit():
        abort(400)
    try:
        if action == "remove":
            remove_member(h, user)
            msg = f"{user.username} wurde entfernt."
        elif action in ("owner", "member"):
            set_role(h, user, ROLE_OWNER if action == "owner" else ROLE_MEMBER)
            msg = f"Rolle von {user.username} geändert."
        else:
            abort(404)
        db.session.commit()
        flash(msg, "success")
    except MembershipError as e:
        db.session.rollback()
        flash(str(e), "danger")
    if user.id == current_user.id and action == "remove":
        return redirect(url_for("main.index"))
    return redirect(url_for("main.household_settings", id=id))


@bp.route("/households/<int:id>/leave", methods=["POST"])
@login_required
def leave_household(id):
    h = household_for(current_user, id)
    if not EmptyForm().validate_on_submit():
        abort(400)
    try:
        remove_member(h, current_user)
        db.session.commit()
        flash(f"Du hast «{h.name}» verlassen.", "info")
        return redirect(url_for("main.index"))
    except MembershipError as e:
        db.session.rollback()
        flash(str(e) + " Ernenne zuerst jemand anderen zum Besitzer.", "danger")
        return redirect(url_for("main.household", id=id))


@bp.route("/households/<int:id>/plan")
@login_required
def household_plan(id):
    h = household_for(current_user, id)
    order, leftovers = suggested_order(h.projects)
    return render_template("main/plan.html", title="Planung", household=h,
                           plan=budget_proposal(h), order=order, leftovers=leftovers,
                           accuracy=estimation_accuracy(h))


# ---------------------------------------------------------------------------
# Projekte
# ---------------------------------------------------------------------------
@bp.route("/households/<int:id>/projects/new", methods=["GET", "POST"])
@login_required
def new_project(id):
    h = household_for(current_user, id)
    form = ProjectForm()
    if form.validate_on_submit():
        p = Project(household=h, created_by=current_user, title=form.title.data.strip(),
                    description=form.description.data or None,
                    estimated_cost=_dec(form.estimated_cost.data),
                    estimated_hours=_dec(form.estimated_hours.data))
        db.session.add(p)
        db.session.commit()
        flash("Idee erfasst. Bewerte sie gleich selbst!", "success")
        return redirect(url_for("main.project", id=p.id))
    return render_template("main/project_form.html", title="Neue Idee", household=h, form=form)


@bp.route("/projects/<int:id>")
@login_required
def project(id):
    p = project_for(current_user, id)
    h = p.household
    score = compute_project_score(p)
    my_values = {r.criterion_id: r.value for r in p.ratings if r.user_id == current_user.id}
    # Mögliche neue Abhängigkeiten: offene Projekte desselben Haushalts ausser sich selbst
    candidates = [x for x in h.projects
                  if x.id != p.id and x not in p.dependencies and x.status != "verworfen"]
    return render_template("main/project.html", title=p.title, project=p, household=h, score=score,
                           my_values=my_values, actions=allowed_actions(p),
                           can_rate=p.status in RATABLE_STATUSES, candidates=candidates,
                           can_delete=can_delete_project(current_user, p), empty_form=EmptyForm())


@bp.route("/projects/<int:id>/edit", methods=["GET", "POST"])
@login_required
def edit_project(id):
    p = project_for(current_user, id)
    if p.status == STATUS_ERLEDIGT:
        flash("Abgeschlossene Projekte können nicht mehr bearbeitet werden.", "warning")
        return redirect(url_for("main.project", id=id))
    form = ProjectForm(obj=p if request.method == "GET" else None)
    if form.validate_on_submit():
        p.title = form.title.data.strip()
        p.description = form.description.data or None
        p.estimated_cost = _dec(form.estimated_cost.data)
        p.estimated_hours = _dec(form.estimated_hours.data)
        db.session.commit()
        flash("Projekt gespeichert.", "success")
        return redirect(url_for("main.project", id=id))
    return render_template("main/project_form.html", title="Projekt bearbeiten",
                           household=p.household, form=form, project=p)


@bp.route("/projects/<int:id>/delete", methods=["POST"])
@login_required
def delete_project(id):
    p = project_for(current_user, id)
    if not can_delete_project(current_user, p):
        abort(403)
    if [d for d in p.dependents if d.is_open]:
        flash("Andere offene Projekte hängen davon ab – zuerst die Abhängigkeit entfernen.", "danger")
        return redirect(url_for("main.project", id=id))
    if EmptyForm().validate_on_submit():
        hid, title = p.household_id, p.title
        db.session.delete(p)
        db.session.commit()
        flash(f"Projekt «{title}» gelöscht.", "info")
        return redirect(url_for("main.household", id=hid))
    abort(400)


@bp.route("/projects/<int:id>/rate", methods=["POST"])
@login_required
def rate_project(id):
    p = project_for(current_user, id)
    if not EmptyForm().validate_on_submit():
        abort(400)
    values = {k[2:]: v for k, v in request.form.items() if k.startswith("c_")}
    try:
        changed = save_ratings(p, current_user, values)
        db.session.commit()
        flash("Bewertung gespeichert.", "success")
        if changed:
            flash("Alle haben bewertet – das Projekt ist jetzt «Bewertet».", "info")
    except RatingError as e:
        db.session.rollback()
        flash(str(e), "danger")
    return redirect(url_for("main.project", id=id))


@bp.route("/projects/<int:id>/status", methods=["POST"])
@login_required
def project_status(id):
    p = project_for(current_user, id)
    if not EmptyForm().validate_on_submit():
        abort(400)
    try:
        change_status(p, request.form.get("target", ""),
                      actual_cost=request.form.get("actual_cost"),
                      actual_hours=request.form.get("actual_hours"))
        db.session.commit()
        flash(f"Status geändert: «{p.status_label}».", "success")
    except WorkflowError as e:
        db.session.rollback()
        flash(str(e), "danger")
    return redirect(url_for("main.project", id=id))


@bp.route("/projects/<int:id>/dependencies", methods=["POST"])
@login_required
def add_project_dependency(id):
    p = project_for(current_user, id)
    if not EmptyForm().validate_on_submit():
        abort(400)
    try:
        dep = project_for(current_user, request.form.get("depends_on", 0, type=int))
        add_dependency(p, dep)
        db.session.commit()
        flash(f"«{p.title}» wartet jetzt auf «{dep.title}».", "success")
    except DependencyError as e:
        db.session.rollback()
        flash(str(e), "danger")
    return redirect(url_for("main.project", id=id))


@bp.route("/projects/<int:id>/dependencies/<int:dep_id>/delete", methods=["POST"])
@login_required
def delete_project_dependency(id, dep_id):
    p = project_for(current_user, id)
    dep = project_for(current_user, dep_id)
    if not EmptyForm().validate_on_submit():
        abort(400)
    try:
        remove_dependency(p, dep)
        db.session.commit()
        flash("Abhängigkeit entfernt.", "info")
    except DependencyError as e:
        flash(str(e), "danger")
    return redirect(url_for("main.project", id=id))


# ---------------------------------------------------------------------------
# Profil / API-Token / Hilfe
# ---------------------------------------------------------------------------
@bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    form = EmptyForm()
    token = None
    if form.validate_on_submit():
        if request.form.get("action") == "revoke":
            current_user.revoke_token()
            flash("Token widerrufen.", "info")
        else:
            token = current_user.get_token(current_app.config["API_TOKEN_LIFETIME"])
        db.session.commit()
    return render_template("main/profile.html", title="Profil & API", form=form, token=token)


@bp.route("/help")
def help():
    return render_template("main/help.html", title="Hilfe")

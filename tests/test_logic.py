"""Tests der Geschäftslogik (app/services). Die IDs T03–T10 entsprechen dem Testprotokoll."""
import pytest

from app import db
from app.models import Household
from app.services.access import MembershipError, remove_member
from app.services.dependencies import DependencyError, add_dependency, suggested_order
from app.services.planning import budget_proposal, estimation_accuracy
from app.services.ratings import RatingError, save_ratings
from app.services.scoring import compute_project_score, weighted_score
from app.services.workflow import WorkflowError, change_status
from tests.conftest import project, rate_all, user


# --- T03 Nutzwert-Score ------------------------------------------------------
def test_T03_weighted_score_with_cost_criterion(household):
    crit = list(household.criteria)  # Nutzen w3, Dringlichkeit w2, Freude w1, Aufwand w2 (Kosten)
    vals = lambda *v: {c.id: x for c, x in zip(crit, v)}  # noqa: E731
    # Teilnutzen 5,4,3,(6-2)=4 -> (15+8+3+8)/8 = 4.25 -> (4.25-1)/4*100 = 81.25
    assert weighted_score(vals(5, 4, 3, 2), crit) == pytest.approx(81.25)
    assert weighted_score(vals(5, 5, 5, 1), crit) == pytest.approx(100)   # bestmöglich
    assert weighted_score(vals(1, 1, 1, 5), crit) == pytest.approx(0)     # schlechtestmöglich
    assert weighted_score(vals(5, 4, 3), crit) is None                    # unvollständig


def test_T03_project_score_is_mean_of_members(household):
    p = project(household, "Lampe")
    rate_all(p, [5, 4, 3, 2], [3, 3, 3, 3])          # 81.25 und 50
    s = compute_project_score(p)
    assert s.score == pytest.approx(65.625)
    assert s.all_rated


# --- T04 Konsens-Erkennung ---------------------------------------------------
def test_T04_disagreement_detected(household):
    p = project(household, "Hochbeet")
    rate_all(p, [5, 2, 5, 3], [2, 1, 2, 4])
    s = compute_project_score(p)
    assert s.disagreement
    assert any("Nutzen" in r for r in s.disagreement_reasons)


def test_T04_no_disagreement_when_similar(household):
    p = project(household, "Fenster")
    rate_all(p, [4, 5, 1, 2], [4, 4, 2, 2])
    assert not compute_project_score(p).disagreement


# --- T05 Validierung der Bewertung -------------------------------------------
@pytest.mark.parametrize("bad", [0, 6, -1, "abc", None])
def test_T05_rating_out_of_range_rejected(household, bad):
    p = project(household, "X")
    crit = list(household.criteria)
    values = {c.id: 3 for c in crit}
    values[crit[0].id] = bad
    with pytest.raises(RatingError):
        save_ratings(p, user("anna"), values)


def test_T05_incomplete_rating_rejected(household):
    p = project(household, "X")
    crit = list(household.criteria)
    with pytest.raises(RatingError, match="fehlt"):
        save_ratings(p, user("anna"), {crit[0].id: 3})


# --- T06 Status-Workflow -----------------------------------------------------
def test_T06_auto_transition_when_all_rated(household):
    p = project(household, "Keller")
    crit = list(household.criteria)
    save_ratings(p, user("anna"), {c.id: 3 for c in crit})
    assert p.status == "idee"                       # ben fehlt noch
    save_ratings(p, user("ben"), {c.id: 4 for c in crit})
    assert p.status == "bewertet"


def test_T06_cannot_skip_states(household):
    p = project(household, "Keller")
    with pytest.raises(WorkflowError):
        change_status(p, "in_arbeit")              # idee -> in_arbeit nicht vorgesehen


def test_T06_finish_requires_actuals(household):
    p = project(household, "Keller", cost=100, hours=5)
    rate_all(p, [3, 3, 3, 3], [3, 3, 3, 3])
    change_status(p, "geplant")
    change_status(p, "in_arbeit")
    with pytest.raises(WorkflowError, match="Ist-Kosten"):
        change_status(p, "erledigt")
    change_status(p, "erledigt", actual_cost="120", actual_hours="6,5")
    assert p.status == "erledigt" and float(p.actual_hours) == 6.5


# --- T07 Abhängigkeiten blockieren Start --------------------------------------
def test_T07_blocked_until_dependency_done(household):
    wand = project(household, "Wand streichen")
    lampe = project(household, "Lampe montieren")
    for p in (wand, lampe):
        rate_all(p, [4, 4, 4, 2], [4, 4, 4, 2])
        change_status(p, "geplant")
    add_dependency(lampe, wand)
    with pytest.raises(WorkflowError, match="Blockiert"):
        change_status(lampe, "in_arbeit")
    change_status(wand, "in_arbeit")
    change_status(wand, "erledigt", actual_cost=0, actual_hours=1)
    change_status(lampe, "in_arbeit")
    assert lampe.status == "in_arbeit"


def test_T07_cannot_discard_needed_project(household):
    wand, lampe = project(household, "Wand"), project(household, "Lampe")
    add_dependency(lampe, wand)
    with pytest.raises(WorkflowError, match="hängen davon ab"):
        change_status(wand, "verworfen")


# --- T08 Zyklen werden erkannt -----------------------------------------------
def test_T08_cycle_rejected(household):
    a, b, c = project(household, "A"), project(household, "B"), project(household, "C")
    add_dependency(a, b)
    add_dependency(b, c)
    with pytest.raises(DependencyError, match="Zirkulär"):
        add_dependency(c, a)                         # C -> A würde A->B->C->A schliessen
    assert a not in c.dependencies


def test_T08_self_and_cross_household_rejected(household):
    a = project(household, "A")
    with pytest.raises(DependencyError):
        add_dependency(a, a)
    other = Household(name="Anderes")
    db.session.add(other)
    db.session.flush()
    x = project(other, "X")
    with pytest.raises(DependencyError, match="Haushalts"):
        add_dependency(a, x)


# --- T09 Topologische Reihenfolge ---------------------------------------------
def test_T09_order_respects_dependencies_and_score(household):
    wand = project(household, "Wand")
    lampe = project(household, "Lampe")
    garten = project(household, "Garten")
    rate_all(wand, [2, 2, 2, 4], [2, 2, 2, 4])        # tiefer Score
    rate_all(lampe, [5, 5, 5, 1], [5, 5, 5, 1])       # hoher Score, aber abhängig
    rate_all(garten, [4, 4, 4, 2], [4, 4, 4, 2])      # mittlerer Score
    add_dependency(lampe, wand)
    order, leftovers = suggested_order(household.projects)
    titles = [o["project"].title for o in order]
    assert leftovers == []
    assert titles.index("Wand") < titles.index("Lampe")
    assert titles[0] == "Garten"                      # frei wählbar und besser als Wand


# --- T10 Budget-Vorschlag -------------------------------------------------------
def test_T10_budget_proposal_respects_limits(household):
    # Budget 1000 CHF, 20 h
    specs = [("Bad", 900, 10, [5, 5, 3, 5]), ("Regal", 200, 3, [4, 3, 4, 2]),
             ("Lampe", 150, 2, [4, 2, 4, 1]), ("Keller", 0, 8, [4, 4, 1, 3]),
             ("Velo", 300, 6, [4, 3, 3, 3])]
    ps = {}
    for title, cost, hours, vals in specs:
        ps[title] = project(household, title, cost, hours)
        rate_all(ps[title], vals, vals)
    add_dependency(ps["Velo"], ps["Keller"])
    plan = budget_proposal(household)
    chosen = {s["project"].title for s in plan["selected"]}
    assert plan["selected_cost"] <= 1000 and plan["selected_hours"] <= 20
    assert "Bad" not in chosen                           # zu teuer neben den anderen
    if "Velo" in chosen:
        assert "Keller" in chosen                        # Abhängigkeit muss mitgewählt sein
    reasons = {s["project"].title: s["reason"] for s in plan["skipped"]}
    assert "Budget" in reasons["Bad"] or "Zeit" in reasons["Bad"]


def test_T10_budget_warning_when_overcommitted(household):
    p = project(household, "Teuer", cost=1500, hours=2)
    rate_all(p, [3, 3, 3, 3], [3, 3, 3, 3])
    change_status(p, "geplant")
    assert any("überschritten" in w for w in budget_proposal(household)["warnings"])


def test_estimation_accuracy(household):
    p = project(household, "Wand", cost=100, hours=10)
    rate_all(p, [3, 3, 3, 3], [3, 3, 3, 3])
    change_status(p, "geplant")
    change_status(p, "in_arbeit")
    change_status(p, "erledigt", actual_cost=140, actual_hours=10)
    acc = estimation_accuracy(household)
    assert acc["cost_deviation_percent"] == 40.0
    assert acc["hours_deviation_percent"] == 0.0


def test_last_owner_cannot_leave(household):
    with pytest.raises(MembershipError):
        remove_member(household, user("anna"))
    remove_member(household, user("ben"))            # normales Mitglied darf gehen
    db.session.commit()
    assert not user("ben").is_member(household)

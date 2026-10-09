"""Geschäftslogik 4: Budget- und Zeitplanung ("Was liegt drin?").

Problem
-------
Aus den bewerteten Projekten soll eine Auswahl gefunden werden, die
innerhalb des Quartalsbudgets (CHF) und der verfügbaren Stunden möglichst
viel Gesamtnutzen (Summe der Scores) bringt. Das ist ein mehrdimensionales
Rucksackproblem (Knapsack). Für die kleinen Mengen in einem Haushalt
genügt eine bewährte Greedy-Heuristik:

    Verbrauch_i  = Kosten_i / Budget + Stunden_i / Stunden_verfügbar
    Effizienz_i  = Score_i / Verbrauch_i            ("Nutzen pro Ressource")

Es wird wiederholt das Projekt mit der höchsten Effizienz gewählt, das
(1) noch in Budget und Zeit passt und (2) keine offenen Abhängigkeiten hat
ausser solchen, die bereits laufen oder schon gewählt wurden.

Projekte "In Arbeit" sind bereits gesetzt und reservieren Budget und Zeit.

Quelle zur Heuristik: Dantzig, G. B. (1957). Discrete-variable extremum
problems. Operations Research, 5(2), 266–288. https://doi.org/10.1287/opre.5.2.266
"""
from app.models import (STATUS_BEWERTET, STATUS_ERLEDIGT, STATUS_GEPLANT,
                        STATUS_IDEE, STATUS_IN_ARBEIT)
from app.services.scoring import compute_project_score

BUDGET_WARNING_THRESHOLD = 1.0   # Warnung, wenn Geplantes > 100 % des Budgets


def _f(value):
    return float(value or 0)


def _consumption(cost, hours, budget, hours_available):
    """Anteil am Budget + Anteil an der Zeit. Unendlich, wenn eine Ressource fehlt."""
    parts = 0.0
    for need, have in ((cost, budget), (hours, hours_available)):
        if need > 0:
            if have <= 0:
                return float("inf")
            parts += need / have
    return parts


def budget_proposal(household):
    """Berechnet den Vorschlag für das Quartal.

    Rückgabe: dict mit selected, skipped, Summen und Warnungen (siehe to_api()).
    """
    budget = _f(household.budget_chf)
    hours = _f(household.hours_available)
    projects = list(household.projects)
    scores = {p.id: compute_project_score(p) for p in projects}

    running = [p for p in projects if p.status == STATUS_IN_ARBEIT]
    reserved_cost = sum(_f(p.estimated_cost) for p in running)
    reserved_hours = sum(_f(p.estimated_hours) for p in running)

    rest_cost = budget - reserved_cost
    rest_hours = hours - reserved_hours

    candidates = [p for p in projects
                  if p.status in (STATUS_BEWERTET, STATUS_GEPLANT) and scores[p.id].score is not None]
    unrated = [p for p in projects if p.status == STATUS_IDEE]

    selected = []
    selected_ids = {p.id for p in running}

    def ready(p):
        return all(d.status == STATUS_ERLEDIGT or d.id in selected_ids for d in p.dependencies)

    def efficiency(p):
        c = _consumption(_f(p.estimated_cost), _f(p.estimated_hours), budget, hours)
        s = scores[p.id].score
        return float("inf") if c == 0 else s / c

    remaining = list(candidates)
    while True:
        fitting = [p for p in remaining
                   if ready(p)
                   and _f(p.estimated_cost) <= rest_cost + 1e-9
                   and _f(p.estimated_hours) <= rest_hours + 1e-9]
        if not fitting:
            break
        best = max(fitting, key=lambda p: (efficiency(p), scores[p.id].score, -p.id))
        selected.append({"project": best, "score": scores[best.id].score,
                         "efficiency": efficiency(best)})
        selected_ids.add(best.id)
        rest_cost -= _f(best.estimated_cost)
        rest_hours -= _f(best.estimated_hours)
        remaining.remove(best)

    skipped = []
    for p in remaining:
        if not ready(p):
            waits = [d.title for d in p.dependencies
                     if d.status != STATUS_ERLEDIGT and d.id not in selected_ids]
            reason = "Wartet auf: " + ", ".join(waits)
        elif _f(p.estimated_cost) > rest_cost + 1e-9:
            reason = f"Budget reicht nicht (braucht CHF {_f(p.estimated_cost):.0f}, frei {max(rest_cost, 0):.0f})"
        else:
            reason = f"Zeit reicht nicht (braucht {_f(p.estimated_hours):.1f} h, frei {max(rest_hours, 0):.1f} h)"
        skipped.append({"project": p, "score": scores[p.id].score, "reason": reason})
    for p in unrated:
        skipped.append({"project": p, "score": None,
                        "reason": "Noch nicht von allen bewertet"})

    # --- Warnungen -------------------------------------------------------
    warnings = []
    committed = [p for p in projects if p.status in (STATUS_GEPLANT, STATUS_IN_ARBEIT)]
    committed_cost = sum(_f(p.estimated_cost) for p in committed)
    committed_hours = sum(_f(p.estimated_hours) for p in committed)
    if budget > 0 and committed_cost > budget * BUDGET_WARNING_THRESHOLD:
        warnings.append(f"Geplante und laufende Projekte kosten CHF {committed_cost:.0f} – "
                        f"das Budget von CHF {budget:.0f} ist um CHF {committed_cost - budget:.0f} überschritten.")
    if hours > 0 and committed_hours > hours * BUDGET_WARNING_THRESHOLD:
        warnings.append(f"Geplante und laufende Projekte brauchen {committed_hours:.1f} h – "
                        f"verfügbar sind nur {hours:.1f} h.")
    if budget <= 0 and hours <= 0:
        warnings.append("Für den Haushalt ist weder Budget noch Zeit erfasst (Einstellungen).")

    sel_cost = sum(_f(s["project"].estimated_cost) for s in selected)
    sel_hours = sum(_f(s["project"].estimated_hours) for s in selected)

    return {
        "budget": budget,
        "hours": hours,
        "reserved": {"projects": running, "cost": reserved_cost, "hours": reserved_hours},
        "selected": selected,
        "skipped": skipped,
        "selected_cost": sel_cost,
        "selected_hours": sel_hours,
        "selected_score_sum": sum(s["score"] for s in selected),
        "remaining_cost": budget - reserved_cost - sel_cost,
        "remaining_hours": hours - reserved_hours - sel_hours,
        "committed_cost": committed_cost,
        "committed_hours": committed_hours,
        "warnings": warnings,
    }


def estimation_accuracy(household):
    """Wie genau schätzt der Haushalt? Durchschnittliche Abweichung Ist vs. Soll in Prozent.

    Positiv = unterschätzt (Ist > Schätzung). Nur abgeschlossene Projekte mit
    Schätzung > 0 zählen.
    """
    done = [p for p in household.projects
            if p.status == STATUS_ERLEDIGT and p.actual_cost is not None and p.actual_hours is not None]

    def avg_dev(pairs):
        devs = [(a - e) / e * 100 for e, a in pairs if e > 0]
        return (sum(devs) / len(devs), len(devs)) if devs else (None, 0)

    cost_dev, n_cost = avg_dev([(_f(p.estimated_cost), _f(p.actual_cost)) for p in done])
    hours_dev, n_hours = avg_dev([(_f(p.estimated_hours), _f(p.actual_hours)) for p in done])

    def sentence(dev, what):
        if dev is None:
            return None
        if abs(dev) < 5:
            return f"{what}: Eure Schätzungen sind sehr genau (±5 %)."
        word = "unterschätzt" if dev > 0 else "überschätzt"
        return f"{what}: Ihr habt im Schnitt um {abs(dev):.0f} % {word}."

    return {
        "completed_projects": len(done),
        "cost_deviation_percent": None if cost_dev is None else round(cost_dev, 1),
        "hours_deviation_percent": None if hours_dev is None else round(hours_dev, 1),
        "samples_cost": n_cost,
        "samples_hours": n_hours,
        "messages": [m for m in (sentence(cost_dev, "Kosten"), sentence(hours_dev, "Zeit")) if m],
    }


def proposal_to_api(p):
    """Serialisierung des Vorschlags für das REST-API."""
    def proj(x):
        return {"id": x.id, "title": x.title, "status": x.status,
                "estimated_cost": _f(x.estimated_cost), "estimated_hours": _f(x.estimated_hours)}
    return {
        "budget_chf": p["budget"],
        "hours_available": p["hours"],
        "reserved_by_running": {"cost": p["reserved"]["cost"], "hours": p["reserved"]["hours"],
                                "projects": [proj(x) for x in p["reserved"]["projects"]]},
        "proposal": [dict(proj(s["project"]), score=round(s["score"], 1)) for s in p["selected"]],
        "not_included": [dict(proj(s["project"]),
                              score=None if s["score"] is None else round(s["score"], 1),
                              reason=s["reason"]) for s in p["skipped"]],
        "total_cost": p["selected_cost"],
        "total_hours": p["selected_hours"],
        "remaining_cost": p["remaining_cost"],
        "remaining_hours": p["remaining_hours"],
        "warnings": p["warnings"],
    }


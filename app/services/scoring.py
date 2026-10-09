"""Geschäftslogik 1: Gemeinsame Bewertung als gewichtete Nutzwertanalyse.

Methode
-------
Jedes Haushaltsmitglied bewertet ein Projekt pro Kriterium auf einer Skala
von 1 bis 5. Kriterien haben ein Gewicht (1..5) und eine Richtung:

* benefit (Nutzen):  5 = sehr gut         -> Wert wird direkt verwendet
* cost    (Aufwand): 5 = sehr aufwändig   -> Wert wird umgekehrt (6 - Wert)

Der Score einer Person ist der gewichtete Mittelwert, linear auf 0..100
umgerechnet:

    teilnutzen_k = v_k            (benefit)   bzw.   6 - v_k   (cost)
    mittel       = Summe(g_k * teilnutzen_k) / Summe(g_k)          (1..5)
    score        = (mittel - 1) / 4 * 100                          (0..100)

Der Projekt-Score ist der Mittelwert der Scores aller Personen, die das
Projekt *vollständig* (alle Kriterien) bewertet haben.

Konsens-Erkennung ("Diskussionsbedarf")
---------------------------------------
Ein Projekt wird markiert, wenn
* die persönlichen Scores um mehr als DISAGREEMENT_SCORE_GAP Punkte
  auseinanderliegen, oder
* bei einem einzelnen Kriterium die Bewertungen um mindestens
  DISAGREEMENT_CRITERION_SPREAD Stufen auseinanderliegen (z. B. 1 vs. 4).

Quelle zur Methode: Zangemeister, C. (1976). Nutzwertanalyse in der
Systemtechnik. 4. Aufl., München: Wittemannsche Buchhandlung.
"""
from dataclasses import dataclass, field

from app.models import DIRECTION_COST

DISAGREEMENT_SCORE_GAP = 25.0       # Punkte auf der 0..100-Skala
DISAGREEMENT_CRITERION_SPREAD = 3   # Stufen auf der 1..5-Skala
MIN_VALUE, MAX_VALUE = 1, 5


@dataclass
class ProjectScore:
    score: float | None                 # None = noch niemand vollständig bewertet
    user_scores: dict = field(default_factory=dict)   # {user_id: score}
    complete_raters: set = field(default_factory=set)
    missing_raters: list = field(default_factory=list)  # User-Objekte ohne vollständige Bewertung
    disagreement: bool = False
    disagreement_reasons: list = field(default_factory=list)

    @property
    def all_rated(self):
        return not self.missing_raters and bool(self.complete_raters)

    def to_dict(self):
        return {
            "score": None if self.score is None else round(self.score, 1),
            "user_scores": {str(k): round(v, 1) for k, v in self.user_scores.items()},
            "all_members_rated": self.all_rated,
            "missing_raters": [u.username for u in self.missing_raters],
            "disagreement": self.disagreement,
            "disagreement_reasons": self.disagreement_reasons,
        }


def validate_value(value):
    """Prüft einen einzelnen Bewertungswert. Wirft ValueError bei ungültiger Eingabe."""
    try:
        v = int(value)
    except (TypeError, ValueError):
        raise ValueError("Bewertung muss eine ganze Zahl sein.")
    if not MIN_VALUE <= v <= MAX_VALUE:
        raise ValueError(f"Bewertung muss zwischen {MIN_VALUE} und {MAX_VALUE} liegen.")
    return v


def partial_utility(value, direction):
    """Teilnutzen eines Werts: Kosten-Kriterien werden umgekehrt."""
    return (MAX_VALUE + MIN_VALUE - value) if direction == DIRECTION_COST else value


def weighted_score(values_by_criterion, criteria):
    """Score 0..100 einer Person.

    values_by_criterion: {criterion_id: wert}
    criteria: Liste von Criterion-Objekten (muss alle Kriterien enthalten)
    Gibt None zurück, wenn nicht alle Kriterien bewertet sind.
    """
    if not criteria:
        return None
    total_weight = 0
    total = 0
    for c in criteria:
        if c.id not in values_by_criterion:
            return None
        total += c.weight * partial_utility(values_by_criterion[c.id], c.direction)
        total_weight += c.weight
    mean = total / total_weight
    return (mean - MIN_VALUE) / (MAX_VALUE - MIN_VALUE) * 100


def compute_project_score(project):
    """Berechnet Score, Einzelscores und Konsens für ein Projekt."""
    household = project.household
    criteria = list(household.criteria)
    members = household.members

    # Bewertungen pro Person sammeln: {user_id: {criterion_id: wert}}
    by_user = {}
    for r in project.ratings:
        by_user.setdefault(r.user_id, {})[r.criterion_id] = r.value

    result = ProjectScore(score=None)
    for user in members:
        s = weighted_score(by_user.get(user.id, {}), criteria)
        if s is None:
            result.missing_raters.append(user)
        else:
            result.user_scores[user.id] = s
            result.complete_raters.add(user.id)

    if result.user_scores:
        scores = list(result.user_scores.values())
        result.score = sum(scores) / len(scores)

        # --- Konsens prüfen (nur sinnvoll ab zwei Personen) ---
        if len(scores) >= 2:
            gap = max(scores) - min(scores)
            if gap > DISAGREEMENT_SCORE_GAP:
                result.disagreement_reasons.append(
                    f"Gesamtbewertungen liegen {gap:.0f} Punkte auseinander.")
            for c in criteria:
                vals = [by_user[uid][c.id] for uid in result.complete_raters]
                spread = max(vals) - min(vals)
                if spread >= DISAGREEMENT_CRITERION_SPREAD:
                    result.disagreement_reasons.append(
                        f"Uneinig bei «{c.name}» ({min(vals)} vs. {max(vals)}).")
            result.disagreement = bool(result.disagreement_reasons)

    return result


def rank_projects(projects):
    """Sortiert Projekte nach Score absteigend; unbewertete ans Ende.

    Gibt eine Liste von (project, ProjectScore) zurück.
    """
    scored = [(p, compute_project_score(p)) for p in projects]
    scored.sort(key=lambda t: (t[1].score is None, -(t[1].score or 0), t[0].title.lower()))
    return scored

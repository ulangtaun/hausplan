"""Geschäftslogik 3: Abhängigkeiten zwischen Projekten.

Die Abhängigkeiten bilden einen gerichteten Graphen (Kante A -> B bedeutet
"A hängt ab von B", B muss also zuerst erledigt werden). Damit eine sinnvolle
Reihenfolge existiert, muss der Graph zyklenfrei sein (DAG).

* add_dependency()     prüft Regeln und lehnt Zyklen ab (Tiefensuche)
* suggested_order()    berechnet eine Reihenfolge per topologischer Sortierung
                       (Algorithmus von Kahn); bei Gleichstand gewinnt der
                       höhere Score.

Quellen:
* Kahn, A. B. (1962). Topological sorting of large networks.
  Communications of the ACM, 5(11), 558–562. https://doi.org/10.1145/368996.369025
* Cormen, T. H. et al. (2022). Introduction to Algorithms (4. Aufl.), Kap. 20.3–20.4
  (Tiefensuche, topologisches Sortieren). MIT Press.
"""
import heapq

from app.models import OPEN_STATUSES, STATUS_IN_ARBEIT, STATUS_VERWORFEN
from app.services.scoring import compute_project_score


class DependencyError(Exception):
    """Abhängigkeit ist nicht erlaubt. Die Meldung ist für Benutzer gedacht."""


def find_cycle_path(project, depends_on):
    """Liefert den Pfad depends_on -> ... -> project, falls die neue Kante einen Zyklus bilden würde."""
    # DFS mit Pfadverfolgung, nur für eine verständliche Fehlermeldung
    stack = [(depends_on, [depends_on])]
    seen = set()
    while stack:
        node, path = stack.pop()
        if node.id == project.id:
            return path
        if node.id in seen:
            continue
        seen.add(node.id)
        for d in node.dependencies:
            stack.append((d, path + [d]))
    return None


def add_dependency(project, depends_on):
    """Fügt "project hängt ab von depends_on" hinzu oder wirft DependencyError."""
    if project.id == depends_on.id:
        raise DependencyError("Ein Projekt kann nicht von sich selbst abhängen.")
    if project.household_id != depends_on.household_id:
        raise DependencyError("Abhängigkeiten sind nur innerhalb desselben Haushalts möglich.")
    if depends_on in project.dependencies:
        raise DependencyError(f"«{project.title}» hängt bereits von «{depends_on.title}» ab.")
    if depends_on.status == STATUS_VERWORFEN:
        raise DependencyError("Von einem verworfenen Projekt kann nichts abhängen.")
    if project.status not in OPEN_STATUSES or project.status == STATUS_IN_ARBEIT:
        raise DependencyError("Abhängigkeiten können nur vor dem Start eines Projekts erfasst werden.")

    path = find_cycle_path(project, depends_on)
    if path is not None:
        chain = " → ".join(f"«{p.title}»" for p in [project] + path)
        raise DependencyError(f"Zirkuläre Abhängigkeit: {chain}.")

    project.dependencies.append(depends_on)


def remove_dependency(project, depends_on):
    if depends_on not in project.dependencies:
        raise DependencyError("Diese Abhängigkeit existiert nicht.")
    project.dependencies.remove(depends_on)


def suggested_order(projects, scores=None):
    """Topologische Sortierung der offenen Projekte (Kahn), Score als Tie-Breaker.

    projects: alle Projekte eines Haushalts
    scores:   optional {project_id: score} (sonst wird berechnet)
    Rückgabe: (reihenfolge, zyklus_projekte)
        reihenfolge: Liste von dicts {project, step, blocked_by}
        zyklus_projekte: Projekte, die wegen eines (eigentlich verhinderten)
                         Zyklus nicht sortiert werden konnten -> sollte leer sein.
    """
    open_projects = [p for p in projects if p.status in OPEN_STATUSES]
    ids = {p.id for p in open_projects}
    if scores is None:
        scores = {p.id: compute_project_score(p).score for p in open_projects}

    # Eingangsgrad = Anzahl offener Abhängigkeiten (erledigte zählen als erfüllt)
    indegree = {p.id: 0 for p in open_projects}
    for p in open_projects:
        indegree[p.id] = sum(1 for d in p.dependencies if d.id in ids)

    def priority(p):
        # heapq ist ein Min-Heap -> negativer Score; "In Arbeit" zuerst
        s = scores.get(p.id)
        return (0 if p.status == STATUS_IN_ARBEIT else 1, -(s if s is not None else -1), p.title.lower(), p.id)

    by_id = {p.id: p for p in open_projects}
    heap = [(priority(p), p.id) for p in open_projects if indegree[p.id] == 0]
    heapq.heapify(heap)

    order = []
    while heap:
        _, pid = heapq.heappop(heap)
        p = by_id[pid]
        order.append({
            "project": p,
            "step": len(order) + 1,
            "score": scores.get(p.id),
            "waits_for": [d for d in p.dependencies if d.id in ids],
        })
        for dependent in p.dependents:
            if dependent.id in indegree:
                indegree[dependent.id] -= 1
                if indegree[dependent.id] == 0:
                    heapq.heappush(heap, (priority(dependent), dependent.id))

    sorted_ids = {o["project"].id for o in order}
    leftovers = [p for p in open_projects if p.id not in sorted_ids]
    return order, leftovers

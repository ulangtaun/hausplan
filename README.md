# HausPlan

**Gemeinsam entscheiden, was zuhause als Nächstes gemacht wird.**
Praxisarbeit DBWE (ipso! HF Informatik) – Webanwendung mit Flask und PostgreSQL.

HausPlan ist ein Projekt-Board für Haushalte. Alle Mitglieder bewerten Ideen nach gewichteten Kriterien
(Nutzwertanalyse); die App erkennt Uneinigkeit, verwaltet Abhängigkeiten zwischen Projekten, schlägt eine
Reihenfolge vor und berechnet, welche Projekte ins Quartalsbudget passen.

| | |
|---|---|
| Webanwendung | `https://hausplan.nuscnet.ch` (Port 443) |
| API | `https://hausplan.nuscnet.ch/api/…` – siehe [docs/api.md](docs/api.md) |
| Testkonten | `examinator` (Besitzer der Demo-Wohnung), `mitbewohner` – Passwort siehe Abgabedokument |

## Funktionen

* Registrierung und Login (Flask-Login), Haushalte mit Rollen Besitzer/Mitglied
* Projekte erfassen, bearbeiten, löschen; Kanban-Board nach Status
* **Gewichtete Nutzwertanalyse** mit eigenen Kriterien und Kosten-Kriterien, Score 0–100
* **Konsens-Erkennung** («Diskussionsbedarf») bei stark abweichenden Bewertungen
* **Status-Workflow** mit Regeln (automatisch «Bewertet», Start nur ohne offene Abhängigkeiten, …)
* **Abhängigkeiten** mit Zyklenerkennung und **topologischer Sortierung**
* **Budget-Vorschlag** «Was liegt drin?» (Greedy-Heuristik) und **Schätzgenauigkeit**
* **REST-API** mit Token-Authentifizierung (Flask-HTTPAuth), lesend und Erfassen von Ideen

## Lokal starten

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
flask db upgrade                     # ohne .env wird SQLite (hausplan.db) verwendet
flask seed --password 'Demo2026!'    # Demo-Daten
flask run                            # http://127.0.0.1:5000
```

## Tests

```bash
python -m pytest -v                  # 30 Tests, siehe docs/testprotokoll.md
```

## Dokumentation

| Datei | Inhalt |
|---|---|
| [docs/Praxisarbeit_DBWE.TA1A.PA_HausPlan_Nury_Schmed.pdf](docs/Praxisarbeit_DBWE.TA1A.PA_HausPlan_Nury_Schmed.pdf) | Lösungsdokument der Praxisarbeit (PDF) |
| [docs/architektur.md](docs/architektur.md) | Code-Struktur, ERD, Zustands-, Sequenz-, Aktivitäts- und Bereitstellungsdiagramm, Technologien, Quellen, Reflexion |
| [docs/diagramme/](docs/diagramme) | Diagramme als PNG und SVG für das PDF |
| [docs/api.md](docs/api.md) | API-Endpunkte im Format `<Methode> <URL>` mit Beispielen |
| [docs/benutzerhandbuch.md](docs/benutzerhandbuch.md) | Bedienung im Browser |
| [docs/testprotokoll.md](docs/testprotokoll.md) | 12 + 3 Testfälle mit erwartetem und tatsächlichem Ergebnis |
| [docs/deployment.md](docs/deployment.md) | Proxmox-LXC, PostgreSQL, Gunicorn, Nginx, Cloudflare Tunnel, Backups |

## Technologien

Python 3.11+ · Flask 3 · Flask-SQLAlchemy · Flask-Migrate · Flask-Login · Flask-WTF · Flask-HTTPAuth ·
PostgreSQL · Gunicorn · Nginx · Cloudflare Tunnel · Proxmox VE (LXC) · Bootstrap 5 · pytest

## Quellen

* Grinberg, M. *The Flask Mega-Tutorial* (2024). https://blog.miguelgrinberg.com/post/the-flask-mega-tutorial-part-i-hello-world
  – Grundstruktur (Application Factory, Blueprints, Login, Token-API). Abweichungen sind im Code kommentiert.
* Weitere Quellen zu Algorithmen und Technologien: [docs/architektur.md](docs/architektur.md), Kap. 7 und 8.

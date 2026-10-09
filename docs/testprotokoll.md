# Testprotokoll HausPlan

Automatisierte Tests: `python -m pytest -v` (pytest, In-Memory-Datenbank, frisch pro Test).
Stand der automatisierten Durchführung: **09.10.2026, lokal, 30 von 30 Tests bestanden.**

Die Tests T01–T12 decken die Anforderungen aus der Aufgabenstellung (2.1.1) und die eigene
Geschäftslogik ab. Die Tests M01–M03 werden nach dem Deployment manuell über das Internet ausgeführt.

| ID | Anforderung | Kurzbeschreibung | Erwartetes Ergebnis | Tatsächliches Ergebnis | Status |
|---|---|---|---|---|---|
| T01 | Registrierung mit eindeutigem Benutzernamen und E-Mail | Neues Konto «nury» anlegen; danach «Nury» (andere Schreibweise) und dieselbe E-Mail erneut registrieren; Passwort mit 3 Zeichen | Erstes Konto wird angelegt; Duplikate werden mit «bereits vergeben» / «bereits registriert» abgelehnt; kurzes Passwort mit «Mindestens 8 Zeichen» | Wie erwartet | ✅ |
| T02 | Zugriff nur mit Benutzerkonto | Haushaltsseite ohne Login aufrufen; Login mit falschem Passwort; Login korrekt | Weiterleitung auf Login; Fehlermeldung; danach Haushalt sichtbar | Wie erwartet | ✅ |
| T03 | Geschäftslogik: Nutzwert-Score | Bewertung 5/4/3/2 bei Gewichten 3/2/1/2, «Aufwand» als Kosten-Kriterium | Score 81,25; Bestwert 100, Schlechtester 0; zwei Personen (81,25 und 50) → Projekt-Score 65,6 | 81,25 / 100 / 0 / 65,625 | ✅ |
| T04 | Geschäftslogik: Konsens-Erkennung | Zwei Personen bewerten «Hochbeet» sehr unterschiedlich (Nutzen 5 vs. 2) bzw. ähnlich | Flag «Diskussionsbedarf» mit Grund «Uneinig bei Nutzen»; bei ähnlichen Werten kein Flag | Wie erwartet | ✅ |
| T05 | Eingabeprüfung Bewertung | Werte 0, 6, −1, «abc», leer sowie unvollständige Bewertung speichern | Jede Eingabe wird abgelehnt, nichts gespeichert | Alle 6 Fälle abgelehnt | ✅ |
| T06 | Status-Workflow | Erste Person bewertet → Status bleibt «Idee»; zweite bewertet → «Bewertet». Sprung Idee → In Arbeit; Abschliessen ohne Ist-Werte | Automatischer Wechsel auf «Bewertet»; unerlaubter Sprung und Abschluss ohne Ist-Werte werden abgelehnt; mit «6,5» Stunden klappt Abschluss | Wie erwartet | ✅ |
| T07 | Abhängigkeit blockiert Start | «Lampe» hängt von «Wand» ab; Lampe starten; Wand abschliessen; Lampe erneut starten. Wand verwerfen, solange Lampe offen ist | Erster Start mit «Blockiert durch …» abgelehnt, danach erlaubt; Verwerfen abgelehnt | Wie erwartet | ✅ |
| T08 | Zyklenerkennung | A→B, B→C anlegen, dann C→A; Projekt von sich selbst abhängig machen; Abhängigkeit zu fremdem Haushalt | «Zirkuläre Abhängigkeit: C → A → B → C» bzw. Fehlermeldung, nichts gespeichert | Wie erwartet | ✅ |
| T09 | Empfohlene Reihenfolge | Wand (tiefer Score) ← Lampe (hoher Score), Garten (mittel, unabhängig) | Reihenfolge Garten, Wand, Lampe; Wand immer vor Lampe | Wie erwartet | ✅ |
| T10 | Budget-Vorschlag | Budget 1000 CHF / 20 h, fünf Projekte, «Velo» hängt von «Keller» ab, «Bad» kostet 900 CHF | Summe ≤ 1000 CHF und ≤ 20 h; Bad nicht gewählt mit Grund «Budget reicht nicht»; Velo nur zusammen mit Keller; Warnung, wenn Geplantes > Budget | Gewählt: Lampe, Regal, Keller, Velo (650 CHF, 19 h); Bad mit Grund ausgeschlossen; Warnung erscheint | ✅ |
| T11 | API: Authentifizierung ohne Browser, Daten lesen | Ohne Token `GET /api/households`; Token mit falschem Passwort; Token holen; Projekte, Ranking, Reihenfolge, Plan, Statistik, Projektdetail abrufen; Token widerrufen | 401; 401; 200 mit Token; alle Endpunkte 200 mit korrekten Daten (Score 65,6); nach Widerruf 401 | Wie erwartet | ✅ |
| T12 | API: Berechtigung | Benutzer «fremd» ruft Projekte eines fremden Haushalts und ein fremdes Projekt ab; nicht existierendes Projekt | 403 als JSON; 403; 404 | Wie erwartet | ✅ |
| M01 | Bereitstellung im Internet (Browser) | `https://hausplan.<domain>.ch` von einem externen Netz (Handy-Hotspot) öffnen, mit Testkonto anmelden | Login-Seite über HTTPS, Board der Demo-Wohnung sichtbar | *nach Deployment ausfüllen* | ⏳ |
| M02 | Bereitstellung im Internet (API) | `curl -u examinator:… -X POST https://hausplan.<domain>.ch/api/tokens` von extern | JSON mit Token, keine Cloudflare-Challenge-Seite | *nach Deployment ausfüllen* | ⏳ |
| M03 | Verfügbarkeit nach Neustart | Proxmox-Node neu starten | Beide Container starten automatisch (DB zuerst), App nach < 2 min wieder erreichbar | *nach Deployment ausfüllen* | ⏳ |

Zusätzliche automatisierte Tests (nicht im Protokoll ausgewählt): Schätzgenauigkeit (+40 % bei 100 → 140 CHF),
letzter Besitzer kann Haushalt nicht verlassen, Web-Ablauf «Idee erfassen und bewerten»,
fremder Haushalt im Web gibt 403, API-Filter und Erfassen einer Idee per `POST` inkl. Validierung.

Zuordnung zum Code: `tests/test_logic.py` (T03–T10) und `tests/test_web_api.py` (T01, T02, T11, T12);
der Testname beginnt jeweils mit der ID.

# Benutzerhandbuch HausPlan

HausPlan hilft einem Haushalt, Ideen und Projekte für zuhause gemeinsam zu sammeln, fair zu
bewerten und realistisch zu planen.

## Anmelden und Registrieren

* **Registrieren**: Benutzername (eindeutig), E-Mail (eindeutig) und Passwort (mind. 8 Zeichen).
* **Anmelden**: mit Benutzername und Passwort. Ohne Anmeldung ist nur die Hilfeseite sichtbar.

## Haushalt einrichten

1. Auf der Startseite unter **Neuer Haushalt** Namen, Budget pro Quartal (CHF) und verfügbare
   Stunden pro Quartal eingeben. Du wirst automatisch **Besitzer**.
2. Unter **Einstellungen → Mitglieder** weitere Personen über ihren Benutzernamen hinzufügen
   (sie müssen sich vorher registriert haben).
3. Unter **Einstellungen → Bewertungskriterien** die vier Standard-Kriterien (Nutzen, Dringlichkeit,
   Freude, Aufwand) anpassen: Gewicht 1–5 ändern, Kriterien hinzufügen oder löschen.
   Bei einem **Kosten-Kriterium** (z. B. Aufwand) ist ein hoher Wert schlecht.

## Mit Projekten arbeiten

Das **Board** zeigt alle offenen Projekte in Spalten nach Status, innerhalb der Spalte nach Score sortiert.

| Symbol | Bedeutung |
|---|---|
| farbige Zahl | Gemeinsamer Score 0–100 (rot = tief, grün = hoch) |
| 💬 Diskussion | Ihr seid euch bei diesem Projekt deutlich uneinig |
| 🔒 blockiert | Ein Projekt, von dem dieses abhängt, ist noch nicht erledigt |

1. **+ Neue Idee**: Titel, Beschreibung, geschätzte Kosten und Stunden.
2. **Bewerten**: Im Projekt pro Kriterium 1–5 wählen und speichern. Haben alle Mitglieder bewertet,
   wechselt das Projekt automatisch auf **Bewertet**.
3. **Abhängigkeiten**: «Hängt ab von» wählen. HausPlan verhindert Kreise (A wartet auf B, B auf A).
4. **Status**: Einplanen → Starten → Abschliessen (mit effektiven Kosten und Stunden).
   Ist ein Schritt nicht möglich, ist der Button grau und der Grund steht darunter.
   Projekte können verworfen und später reaktiviert werden.

## Planung

Unter **Planung** zeigt HausPlan:

* **Was liegt drin?** – welche bewerteten Projekte ins Quartalsbudget und die verfügbare Zeit passen,
  mit dem meisten Nutzen pro Franken und Stunde. Nicht gewählte Projekte sind mit Grund aufgeführt.
* **Empfohlene Reihenfolge** – berücksichtigt Abhängigkeiten, sonst kommt der höhere Score zuerst.
* **Schätzgenauigkeit** – wie stark eure Schätzungen bei abgeschlossenen Projekten daneben lagen.

## API-Zugang

Unter **Profil & API** kannst du ein Token anzeigen lassen oder widerrufen. Details: `docs/api.md`
oder die Seite **Hilfe & API** in der App.

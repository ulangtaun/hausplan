# REST-API von HausPlan

Basis-URL: `https://hausplan.<deine-domain>.ch` (Port 443). Alle Antworten sind JSON.
Die Beispiele verwenden [HTTPie](https://httpie.io) (`http`) und `curl`.

## Authentifizierung (ohne Browser)

1. Mit Benutzername und Passwort (HTTP Basic Auth) ein Token holen.
2. Das Token bei jeder weiteren Anfrage im Header `Authorization: Bearer <token>` mitsenden.

Tokens sind 7 Tage gültig und können widerrufen werden. Umsetzung mit Flask-HTTPAuth
nach Grinberg, *Flask Mega-Tutorial*, Kap. 23.

```bash
http --auth examinator:PASSWORT POST https://host/api/tokens
curl -u examinator:PASSWORT -X POST https://host/api/tokens
# -> {"token": "3f9c…", "expires": "2026-…"}

export T=3f9c…
http GET https://host/api/households "Authorization:Bearer $T"
curl https://host/api/households -H "Authorization: Bearer $T"
```

## Endpunkte

| Methode | Endpunkt | Beschreibung |
|---|---|---|
| `POST` | `/api/tokens` | Token holen (Basic Auth) |
| `DELETE` | `/api/tokens` | Eigenes Token widerrufen |
| `GET` | `/api/users/me` | Eigenes Profil inkl. Haushalte |
| `GET` | `/api/households` | Haushalte, in denen ich Mitglied bin |
| `GET` | `/api/households/<id>` | Haushalt mit Mitgliedern, Rollen, Kriterien, Planungsrahmen |
| `GET` | `/api/households/<id>/projects` | Alle Projekte des Haushalts |
| `GET` | `/api/households/<id>/projects?status=<status>` | Gefiltert: `idee`, `bewertet`, `geplant`, `in_arbeit`, `erledigt`, `verworfen` |
| `POST` | `/api/households/<id>/projects` | Neue Idee erfassen (JSON-Body, siehe unten) |
| `GET` | `/api/households/<id>/ranking` | Offene Projekte nach Nutzwert-Score sortiert |
| `GET` | `/api/households/<id>/order` | Empfohlene Reihenfolge (Abhängigkeiten + Score) |
| `GET` | `/api/households/<id>/plan` | Budget-Vorschlag «Was liegt drin?» |
| `GET` | `/api/households/<id>/stats` | Projekte pro Status, Schätzgenauigkeit |
| `GET` | `/api/projects/<id>` | Projekt mit Einzelbewertungen, Konsens, Abhängigkeiten |

Vollständige Testbefehle (Haushalt 1 = «Demo-Wohnung» aus den Demo-Daten):

```bash
http GET  https://host/api/users/me                         "Authorization:Bearer $T"
http GET  https://host/api/households/1                     "Authorization:Bearer $T"
http GET  https://host/api/households/1/projects status==geplant "Authorization:Bearer $T"
http GET  https://host/api/households/1/ranking             "Authorization:Bearer $T"
http GET  https://host/api/households/1/order               "Authorization:Bearer $T"
http GET  https://host/api/households/1/plan                "Authorization:Bearer $T"
http GET  https://host/api/households/1/stats               "Authorization:Bearer $T"
http GET  https://host/api/projects/4                       "Authorization:Bearer $T"
http POST https://host/api/households/1/projects            "Authorization:Bearer $T" \
          title="Pflanzen umtopfen" estimated_cost:=30 estimated_hours:=1
http DELETE https://host/api/tokens                         "Authorization:Bearer $T"
```

### POST `/api/households/<id>/projects`

```json
{"title": "Pflanzen umtopfen", "description": "optional", "estimated_cost": 30, "estimated_hours": 1}
```

Antwort `201 Created` mit dem neuen Projekt und Header `Location: /api/projects/<id>`.

### Beispielantwort `GET /api/households/1/ranking`

```json
{
  "items": [
    {"rank": 1, "id": 5, "title": "Heizungssteuerung smart machen", "status": "in_arbeit",
     "score": 62.5, "disagreement": true, "estimated_cost": 450.0, "estimated_hours": 10.0,
     "blocked": false, "_links": {"self": "/api/projects/5"}},
    …
  ]
}
```

## Fehlercodes

| Code | Bedeutung |
|---|---|
| 400 | Ungültige Eingabe (z. B. fehlender Titel, negativer Betrag, unbekannter Status) |
| 401 | Kein / ungültiges / abgelaufenes Token bzw. falsches Passwort |
| 403 | Kein Mitglied dieses Haushalts |
| 404 | Ressource existiert nicht |

Beispiel: `{"error": "Forbidden", "message": "Kein Zugriff auf diese Ressource."}`

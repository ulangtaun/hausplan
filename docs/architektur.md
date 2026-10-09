# Architektur von HausPlan

Grundlage für das Kapitel «Anwendung → Architektur» der Praxisarbeit. Die Diagramme sind in
[Mermaid](https://mermaid.js.org) geschrieben; GitHub stellt sie direkt dar. Für das PDF können sie
z. B. mit dem [Mermaid Live Editor](https://mermaid.live) als PNG/SVG exportiert werden
(fertige Exporte liegen in `docs/diagramme/`).

## 1. Schichten und Code-Struktur

```
hausplan/
├── hausplan.py          Einstiegspunkt (Flask-CLI, Gunicorn: hausplan:app)
├── config.py            Konfiguration aus Umgebungsvariablen (.env)
├── app/
│   ├── __init__.py      Application Factory, Erweiterungen, Blueprints, ProxyFix
│   ├── models.py        Datenmodell (SQLAlchemy)
│   ├── services/        GESCHÄFTSLOGIK – unabhängig von Web und API
│   │   ├── scoring.py       Nutzwertanalyse, Konsens-Erkennung, Ranking
│   │   ├── workflow.py      Zustandsautomat mit Regeln (Guards)
│   │   ├── dependencies.py  Abhängigkeiten, Zyklenerkennung, topologische Sortierung
│   │   ├── planning.py      Budget-Vorschlag (Greedy), Schätzgenauigkeit
│   │   ├── ratings.py       Bewertung speichern + Validierung
│   │   └── access.py        Berechtigungen (Mitglied / Besitzer)
│   ├── auth/            Blueprint: Registrierung, Login, Logout
│   ├── main/            Blueprint: Weboberfläche (Formulare mit Flask-WTF)
│   ├── api/             Blueprint: REST-API mit Token-Auth (Flask-HTTPAuth)
│   ├── templates/       Jinja2-Templates (Bootstrap 5, lokal ausgeliefert)
│   └── cli.py           flask seed / flask create-user
├── migrations/          Alembic-Migrationen (Flask-Migrate)
├── tests/               pytest (30 automatisierte Tests)
└── deploy/              systemd, Nginx, cloudflared, Setup- und Backup-Skripte
```

Die Trennung in `services/` ist die wichtigste Abweichung vom Aufbau des Unterrichts: Web-Routen und
API-Endpunkte rufen dieselben Funktionen auf. So gelten die Regeln überall gleich und lassen sich ohne
HTTP direkt testen.

## 2. Datenmodell (ERD)

```mermaid
erDiagram
    USER ||--o{ MEMBERSHIP : "ist Mitglied"
    HOUSEHOLD ||--o{ MEMBERSHIP : "hat"
    HOUSEHOLD ||--o{ CRITERION : "definiert"
    HOUSEHOLD ||--o{ PROJECT : "enthält"
    USER |o--o{ PROJECT : "erfasst"
    PROJECT ||--o{ RATING : "wird bewertet"
    USER ||--o{ RATING : "gibt ab"
    CRITERION ||--o{ RATING : "nach"
    PROJECT ||--o{ PROJECT_DEPENDENCY : "hängt ab von"
    PROJECT ||--o{ PROJECT_DEPENDENCY : "wird benötigt von"

    USER {
        int id PK
        string username UK
        string email UK
        string password_hash
        string token UK
        datetime token_expiration
        datetime created_at
    }
    HOUSEHOLD {
        int id PK
        string name
        decimal budget_chf "pro Quartal, >= 0"
        decimal hours_available "pro Quartal, >= 0"
        datetime created_at
    }
    MEMBERSHIP {
        int user_id PK,FK
        int household_id PK,FK
        string role "owner | member"
        datetime joined_at
    }
    CRITERION {
        int id PK
        int household_id FK
        string name "eindeutig je Haushalt"
        string description
        int weight "1..5"
        string direction "benefit | cost"
    }
    PROJECT {
        int id PK
        int household_id FK
        int created_by_id FK
        string title
        text description
        string status "idee .. verworfen"
        decimal estimated_cost
        decimal estimated_hours
        decimal actual_cost
        decimal actual_hours
        datetime created_at
        datetime started_at
        datetime completed_at
    }
    RATING {
        int id PK
        int project_id FK
        int user_id FK
        int criterion_id FK
        int value "1..5"
        datetime updated_at
    }
    PROJECT_DEPENDENCY {
        int project_id PK,FK
        int depends_on_id PK,FK
    }
```

**Beschreibung:**

* **User ↔ Household (n:m)** über die Assoziationstabelle `membership` mit dem Zusatzattribut `role`.
  Eine Person kann in mehreren Haushalten sein (z. B. eigene Wohnung und WG des Bruders).
* **Criterion** gehört zu genau einem Haushalt. So kann jeder Haushalt eigene Kriterien und Gewichte festlegen.
* **Rating** ist die Bewertung einer Person für ein Projekt nach einem Kriterium. Der Unique-Constraint
  `(project_id, user_id, criterion_id)` verhindert Doppelbewertungen, ein Check-Constraint erzwingt 1–5.
* **project_dependency** ist eine n:m-Selbstbeziehung von `project` (gleiches Muster wie «Followers» im
  Mega-Tutorial). Zyklenfreiheit kann die Datenbank nicht prüfen; das übernimmt `services/dependencies.py`.
* Check-Constraints in der Datenbank (Status-Werte, Bereiche, nicht-negative Beträge) sichern die
  Datenintegrität zusätzlich zur Validierung in Python ab.

## 3. Zustandsdiagramm: Projekt-Workflow

```mermaid
stateDiagram-v2
    [*] --> Idee : erfassen
    Idee --> Bewertet : automatisch, sobald alle Mitglieder vollständig bewertet haben
    Bewertet --> Geplant : Einplanen [alle haben bewertet]
    Geplant --> Bewertet : Zurückstellen
    Geplant --> InArbeit : Starten [alle Abhängigkeiten erledigt]
    InArbeit --> Geplant : Pausieren
    InArbeit --> Erledigt : Abschliessen [Ist-Kosten und Ist-Stunden erfasst]
    Idee --> Verworfen : Verwerfen [kein offenes Projekt hängt davon ab]
    Bewertet --> Verworfen : Verwerfen [dito]
    Geplant --> Verworfen : Verwerfen [dito]
    InArbeit --> Verworfen : Verwerfen [dito]
    Verworfen --> Idee : Reaktivieren
    Erledigt --> [*]
    state "In Arbeit" as InArbeit
```

Die Bedingungen in eckigen Klammern sind Guards in `services/workflow.py::check_transition()`.
Ist ein Übergang gesperrt, zeigt die Oberfläche den Button deaktiviert mit dem Grund an.

## 4. Sequenzdiagramm: Bewertung abgeben

```mermaid
sequenceDiagram
    actor B as Benutzer (Browser)
    participant R as main/routes.py<br/>rate_project()
    participant S as services/ratings.py<br/>save_ratings()
    participant SC as services/scoring.py
    participant W as services/workflow.py
    participant DB as PostgreSQL

    B->>R: POST /projects/4/rate (c_1=5, c_2=2, …, CSRF-Token)
    R->>R: Login und Mitgliedschaft prüfen (403 sonst)
    R->>S: save_ratings(projekt, user, werte)
    S->>S: Status bewertbar? alle Kriterien? Werte 1..5?
    alt ungültig
        S-->>R: RatingError("Bitte alle Kriterien bewerten …")
        R-->>B: Redirect + Fehlermeldung
    else gültig
        S->>DB: INSERT/UPDATE rating
        S->>W: after_rating_changed(projekt)
        W->>SC: compute_project_score(projekt)
        SC-->>W: Score, fehlende Bewerter, Konsens
        opt alle haben bewertet und Status = Idee
            W->>DB: UPDATE project SET status = 'bewertet'
        end
        R->>DB: COMMIT
        R-->>B: Redirect /projects/4 mit Score und ggf. «Diskussionsbedarf»
    end
```

## 5. Aktivitätsdiagramm: Budget-Vorschlag «Was liegt drin?»

```mermaid
flowchart TD
    A([Start]) --> B[Budget und Stunden des Quartals laden]
    B --> C[Projekte «In Arbeit» reservieren Budget und Zeit]
    C --> D[Kandidaten: Status Bewertet oder Geplant mit Score]
    D --> E{Gibt es einen Kandidaten,<br/>der ins Restbudget passt<br/>und dessen Abhängigkeiten<br/>erledigt, laufend oder gewählt sind?}
    E -- ja --> F[Effizienz berechnen:<br/>Score ÷ Kostenanteil + Zeitanteil]
    F --> G[Kandidat mit höchster Effizienz wählen]
    G --> H[Restbudget und Restzeit reduzieren]
    H --> E
    E -- nein --> I[Nicht gewählte Projekte mit Grund versehen:<br/>Budget / Zeit / wartet auf …]
    I --> J{Geplant + laufend<br/>> Budget oder Zeit?}
    J -- ja --> K[Warnung ausgeben]
    J -- nein --> L([Vorschlag anzeigen])
    K --> L
```

## 6. Bereitstellungsdiagramm

```mermaid
flowchart TB
    subgraph Clients
        BR[Webbrowser]
        CL[API-Client<br/>curl / httpie / Postman]
    end
    subgraph CF[Cloudflare]
        EDGE[hausplan.nuscnet.ch<br/>TLS, DNS, DDoS-Schutz]
    end
    subgraph PVE[Proxmox-Cluster zuhause]
        subgraph APP[LXC 120 hausplan-app · Debian 13]
            CFD[cloudflared]
            NG[Nginx :80<br/>Reverse Proxy, /static]
            GU[Gunicorn :8000<br/>3 Worker]
            FL[Flask-App HausPlan]
        end
        subgraph DBC[LXC 121 hausplan-db · Debian 13]
            PG[(PostgreSQL :5432)]
            BK[pg_dump täglich]
        end
        PBS[Proxmox Backup<br/>vzdump]
    end

    BR -- HTTPS 443 --> EDGE
    CL -- HTTPS 443 --> EDGE
    EDGE <-- Tunnel, nur ausgehend --> CFD
    CFD -- HTTP --> NG
    NG -- HTTP --> GU
    GU --- FL
    FL -- TCP 5432, nur von 192.168.178.220 --> PG
    PG --- BK
    PBS -. sichert .-> APP
    PBS -. sichert .-> DBC
```

| Komponente | Aufgabe |
|---|---|
| Cloudflare Edge | Öffentlicher DNS-Name, TLS-Zertifikat, Schutz vor Angriffen; die Heim-IP bleibt verborgen |
| cloudflared | Baut eine ausgehende Verbindung zu Cloudflare auf; keine Portfreigabe am Router nötig |
| Nginx | Reverse Proxy, liefert statische Dateien aus, setzt die echte Client-IP (`CF-Connecting-IP`) |
| Gunicorn | WSGI-Server mit mehreren Worker-Prozessen, als systemd-Dienst mit automatischem Neustart |
| Flask-App | Weboberfläche, API, Geschäftslogik |
| PostgreSQL | Relationale Datenbank in eigenem Container, nur vom App-Container erreichbar |
| Backups | `pg_dump` (logisch, täglich) und vzdump (ganze Container) |

## 7. Zusätzliche Technologien (nicht im Unterricht) mit Begründung

| Technologie | Wozu | Begründung | Quelle |
|---|---|---|---|
| Proxmox VE (LXC) | Virtualisierung | Vorhandene Infrastruktur, Container getrennt sicherbar und wiederherstellbar | https://pve.proxmox.com/wiki/Linux_Container |
| Cloudflare Tunnel | Veröffentlichung im Internet | Kein offener Port, kostenloses TLS, verbirgt Heim-IP, dynamische IP kein Problem | https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/ |
| Werkzeug ProxyFix | Korrekte Client-IP und Schema hinter Proxy | Ohne ProxyFix generiert Flask falsche URLs (http statt https) | https://flask.palletsprojects.com/en/latest/deploying/proxy_fix/ |
| pytest | Automatisierte Tests | Standard im Python-Umfeld, Fixtures für frische Test-DB | https://docs.pytest.org |
| Bootstrap 5 (lokal) | Gestaltung | Lokal statt CDN ausgeliefert, damit die App nicht von einem fremden Server abhängt | https://getbootstrap.com |

## 8. Algorithmen und Quellen

| Funktion | Verfahren | Quelle |
|---|---|---|
| Score | Gewichtete Nutzwertanalyse, Kosten-Kriterien invertiert, Skala 0–100 | Zangemeister, C. (1976). *Nutzwertanalyse in der Systemtechnik* (4. Aufl.). München: Wittemannsche Buchhandlung. |
| Reihenfolge | Topologische Sortierung nach Kahn mit Prioritätswarteschlange (Score) | Kahn, A. B. (1962). Topological sorting of large networks. *Communications of the ACM, 5*(11), 558–562. |
| Zyklenerkennung | Tiefensuche (DFS) vor dem Einfügen einer Kante | Cormen, T. H. et al. (2022). *Introduction to Algorithms* (4. Aufl.), MIT Press. |
| Budget-Vorschlag | Greedy-Heuristik für das (mehrdimensionale) Rucksackproblem: Nutzen pro Ressourcenanteil | Dantzig, G. B. (1957). Discrete-variable extremum problems. *Operations Research, 5*(2), 266–288. |

## 9. Reflexion – Stichworte

**Wartbarkeit**
* + Geschäftslogik in `services/` gekapselt und mit 30 Tests abgedeckt; Web und API teilen den Code.
* + Datenbankschema versioniert (Alembic), Deployment per Skript reproduzierbar.
* − Server-gerenderte Seiten: Interaktivität begrenzt; mehr JavaScript würde Komplexität erhöhen.

**Skalierbarkeit**
* + Gunicorn-Worker und App-Container sind zustandslos (Sessions im signierten Cookie) und könnten horizontal skaliert werden.
* − Scores werden bei jedem Aufruf berechnet. Für einen Haushalt (≈ 10–100 Projekte) unkritisch; bei
  vielen Projekten wären Caching oder gespeicherte Scores nötig.
* − Greedy liefert nicht immer das Optimum; für exakte Lösungen wäre dynamische Programmierung nötig (bei kleinen Mengen machbar).

**Verfügbarkeit**
* + Automatischer Neustart (systemd `Restart=always`, Proxmox `onboot`), Cloudflare puffert DDoS.
* − Grösstes Risiko: Heimanschluss und Strom sind Single Points of Failure; ohne gemeinsamen Speicher kein HA-Failover.
* − Gegenmassnahmen: Backups (vzdump + pg_dump), Monitoring mit Alarm, dokumentiertes Restore, keine Updates in der Korrekturzeit.

# Bereitstellung auf Proxmox mit Cloudflare Tunnel

Diese Anleitung richtet HausPlan auf zwei LXC-Containern ein und macht die App über einen
Cloudflare Tunnel unter einer eigenen Domain per HTTPS erreichbar. Am Router muss kein Port
geöffnet werden.

```
Internet ──HTTPS──> Cloudflare Edge ──Tunnel (ausgehend)──> cloudflared ─> Nginx :80 ─> Gunicorn :8000 ─> Flask
                                                           └──────────── CT 120 «hausplan-app» ────────────┘
                                                                                                  │ TCP 5432
                                                                                   CT 121 «hausplan-db» (PostgreSQL)
```

Beispielwerte (bitte an dein Netz anpassen):

| Was | Wert |
|---|---|
| App-Container | CT 120, `hausplan-app`, 192.168.1.20 |
| DB-Container | CT 121, `hausplan-db`, 192.168.1.21 |
| Gateway / DNS | 192.168.1.1 |
| Öffentliche Adresse | `https://hausplan.<deine-domain>.ch` |

---

## 0. Voraussetzung: Proxmox-Host hat Internet und DNS

Auf `pv1` schlug `apt` mit *Temporary failure resolving* fehl. Vorher prüfen:

```bash
ping -c2 1.1.1.1          # Netz ok?
ping -c2 deb.debian.org   # DNS ok?
cat /etc/resolv.conf
```

Falls nur DNS fehlt: *Datacenter → pv1 → System → DNS* einen Server eintragen (z. B. `1.1.1.1` oder die Router-IP).
Zusätzlich die doppelte Paketquelle bereinigen (`pve-community.list` und `pve-install-repo.list` zeigen auf dasselbe
Repo) und ohne Subscription das Enterprise-Repo unter *Updates → Repositories* deaktivieren.

## 1. Container anlegen

Template laden (Name der aktuellen Version mit `pveam available` prüfen):

```bash
pveam update
pveam available --section system | grep debian-13
pveam download local debian-13-standard_<version>_amd64.tar.zst
```

Container erstellen. `onboot=1` und `startup` sorgen dafür, dass nach einem Stromausfall zuerst die
Datenbank und dann die App startet – wichtig für die 4 Wochen Korrekturzeit.

```bash
TEMPLATE=local:vztmpl/debian-13-standard_<version>_amd64.tar.zst

pct create 121 $TEMPLATE --hostname hausplan-db --cores 1 --memory 1024 --swap 512 \
  --rootfs local-lvm:8 --net0 name=eth0,bridge=vmbr0,ip=192.168.1.21/24,gw=192.168.1.1 \
  --nameserver 192.168.1.1 --unprivileged 1 --features nesting=1 \
  --onboot 1 --startup order=1,up=20 --password

pct create 120 $TEMPLATE --hostname hausplan-app --cores 2 --memory 1024 --swap 512 \
  --rootfs local-lvm:8 --net0 name=eth0,bridge=vmbr0,ip=192.168.1.20/24,gw=192.168.1.1 \
  --nameserver 192.168.1.1 --unprivileged 1 --features nesting=1 \
  --onboot 1 --startup order=2 --password

pct start 121 && pct start 120
```

> Im Cluster: Container auf dem Node anlegen, der am zuverlässigsten läuft. Ohne gemeinsamen Speicher
> (Ceph/NFS) ist ein automatischer HA-Umzug nicht möglich – das ist ein Punkt für die Reflexion
> zur Verfügbarkeit.

## 2. Datenbank-Container (CT 121)

```bash
pct enter 121
apt-get update && apt-get install -y git
git clone https://github.com/<user>/hausplan.git /root/hausplan
bash /root/hausplan/deploy/setup_db.sh 192.168.1.20 '<starkes-db-passwort>'

# Tägliches Backup
cp /root/hausplan/deploy/backup_db.sh /root/ && chmod +x /root/backup_db.sh
(crontab -l 2>/dev/null; echo "15 3 * * * /root/backup_db.sh") | crontab -
```

## 3. App-Container (CT 120)

```bash
pct enter 120
apt-get update && apt-get install -y git
git clone https://github.com/<user>/hausplan.git /root/hausplan-src
bash /root/hausplan-src/deploy/setup_app.sh https://github.com/<user>/hausplan.git
```

Der erste Lauf legt `/opt/hausplan/.env` mit einem zufälligen `SECRET_KEY` an und bricht ab.
Jetzt die Datenbank eintragen:

```bash
nano /opt/hausplan/.env
# DATABASE_URL=postgresql+psycopg2://hausplan:<starkes-db-passwort>@192.168.1.21/hausplan
# SESSION_COOKIE_SECURE=true
# PROXY_COUNT=1

bash /opt/hausplan/deploy/setup_app.sh https://github.com/<user>/hausplan.git   # zweiter Lauf
cd /opt/hausplan && runuser -u hausplan -- venv/bin/flask seed                  # Demo-Daten + Testkonten
```

Test im LAN: `http://192.168.1.20` im Browser öffnen.

> Hinweis: `SESSION_COOKIE_SECURE=true` bedeutet, dass das Login nur über HTTPS funktioniert. Für einen
> Test im LAN über `http://` vorübergehend auf `false` setzen und `systemctl restart hausplan`.

## 4. Cloudflare Tunnel

### Variante A (empfohlen): Tunnel im Dashboard verwalten

1. Cloudflare Dashboard → **Zero Trust → Networks → Tunnels → Create a tunnel** → Typ *Cloudflared*, Name `hausplan`.
2. Unter *Debian* den angezeigten Installationsbefehl im **App-Container (CT 120)** ausführen
   (installiert das Paket und `cloudflared service install <TOKEN>`).
3. **Public Hostname** hinzufügen: Subdomain `hausplan`, Domain wählen, Service `HTTP` → `localhost:80`.

### Variante B: lokal verwalteter Tunnel

```bash
cloudflared tunnel login
cloudflared tunnel create hausplan
cloudflared tunnel route dns hausplan hausplan.<deine-domain>.ch
# deploy/cloudflared-config.yml nach /etc/cloudflared/config.yml kopieren und UUID eintragen
cloudflared service install
```

Quelle: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/

## 5. Cloudflare-Einstellungen für das API (wichtig!)

Der Examinator testet das API mit `curl`/`httpie`. Cloudflare darf diese Anfragen nicht blockieren:

| Einstellung | Wert | Ort im Dashboard |
|---|---|---|
| Bot Fight Mode | **aus** | Security → Bots |
| Browser Integrity Check | aus oder per Regel für `/api/` überspringen | Security → Settings |
| Cloudflare Access | **keine** Application auf `hausplan.<domain>` (oder `/api/*` ausnehmen) | Zero Trust → Access |
| SSL/TLS | *Full* ist nicht nötig (Tunnel), Standard genügt; «Always Use HTTPS» **an** | SSL/TLS |

Optional eine WAF Custom Rule: *URI Path starts with `/api/`* → **Skip** (alle verwalteten Regeln / Super Bot Fight Mode).

## 6. Abnahmetest von extern (z. B. Handy-Hotspot)

```bash
H=https://hausplan.<deine-domain>.ch
curl -I $H/auth/login                                  # 200
curl -u examinator:'<passwort>' -X POST $H/api/tokens  # {"token": "..."}
curl $H/api/households -H "Authorization: Bearer <token>"
```

## 7. Betrieb während der Korrekturzeit

* **Proxmox-Backup** beider Container (Datacenter → Backup, täglich, `snapshot`-Modus) zusätzlich zum `pg_dump`.
* **Monitoring**: z. B. Uptime Kuma oder ein Cloudflare Health Check auf `https://hausplan.../auth/login`
  mit E-Mail-Benachrichtigung.
* **Keine Updates** am Proxmox-Host oder an den Containern während der Korrekturzeit, ausser Sicherheitsupdates.
* **USV**, falls vorhanden; sonst nach Stromausfall prüfen, ob alles wieder läuft (`onboot`).
* **Restore-Probe** einmal durchspielen: `pg_restore` in eine Test-DB, bzw. Container aus Backup wiederherstellen.

Nützliche Befehle:

```bash
systemctl status hausplan nginx cloudflared
journalctl -u hausplan -f            # App-Log
journalctl -u cloudflared -f         # Tunnel-Log
bash /opt/hausplan/deploy/update_app.sh   # neue Version ausrollen
```

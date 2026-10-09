#!/usr/bin/env bash
# Tägliches logisches Backup der Datenbank (im DB-Container).
# Cron (crontab -e als root):  15 3 * * *  /root/backup_db.sh
# Ergänzt die Proxmox-Backups (vzdump) der ganzen Container.
set -euo pipefail
DIR=/var/backups/hausplan
KEEP_DAYS=14
mkdir -p "$DIR"
runuser -u postgres -- pg_dump -Fc hausplan > "$DIR/hausplan_$(date +%F).dump"
find "$DIR" -name 'hausplan_*.dump' -mtime +$KEEP_DAYS -delete
# Wiederherstellen:  runuser -u postgres -- pg_restore --clean -d hausplan /var/backups/hausplan/hausplan_<datum>.dump

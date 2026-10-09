#!/usr/bin/env bash
# Einrichtung des Datenbank-Containers (Debian 13, PostgreSQL 17).
# Aufruf im DB-Container als root:   bash setup_db.sh <APP_IP> <DB_PASSWORT>
set -euo pipefail
APP_IP="${1:?App-IP fehlt, z. B. 192.168.1.20}"
DB_PW="${2:?Datenbank-Passwort fehlt}"

apt-get update
apt-get install -y postgresql

PGVER=$(ls /etc/postgresql | sort -V | tail -1)
CONF=/etc/postgresql/$PGVER/main

# Benutzer und Datenbank anlegen (idempotent)
runuser -u postgres -- psql -v ON_ERROR_STOP=1 <<SQL
DO \$\$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'hausplan') THEN
    CREATE ROLE hausplan LOGIN PASSWORD '${DB_PW}';
  ELSE
    ALTER ROLE hausplan PASSWORD '${DB_PW}';
  END IF;
END \$\$;
SQL
runuser -u postgres -- psql -tc "SELECT 1 FROM pg_database WHERE datname='hausplan'" | grep -q 1 \
  || runuser -u postgres -- createdb -O hausplan hausplan

# Nur aus dem Netz lauschen und nur den App-Container zulassen
sed -i "s/^#\?listen_addresses.*/listen_addresses = '*'/" $CONF/postgresql.conf
grep -q "hausplan.*${APP_IP}" $CONF/pg_hba.conf || \
  echo "host  hausplan  hausplan  ${APP_IP}/32  scram-sha-256" >> $CONF/pg_hba.conf

systemctl restart postgresql
echo "Fertig. Verbindung: postgresql+psycopg2://hausplan:<pw>@$(hostname -I | awk '{print $1}')/hausplan"

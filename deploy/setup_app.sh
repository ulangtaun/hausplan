#!/usr/bin/env bash
# Einrichtung des App-Containers (Debian 13): Python-venv, Gunicorn, Nginx.
# Aufruf im App-Container als root:   bash setup_app.sh <GIT_URL>
# Danach /opt/hausplan/.env ausfüllen und dieses Skript nochmals starten.
set -euo pipefail
GIT_URL="${1:?Git-URL fehlt, z. B. https://github.com/<user>/hausplan.git}"
APP_DIR=/opt/hausplan

apt-get update
apt-get install -y python3 python3-venv python3-pip git nginx

id hausplan &>/dev/null || useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin hausplan

if [ ! -d "$APP_DIR/.git" ]; then
  git clone "$GIT_URL" "$APP_DIR"
else
  git -C "$APP_DIR" pull --ff-only
fi

python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --upgrade pip
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"

if [ ! -f "$APP_DIR/.env" ]; then
  cp "$APP_DIR/.env.example" "$APP_DIR/.env"
  sed -i "s/^SECRET_KEY=.*/SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')/" "$APP_DIR/.env"
  chown -R hausplan:hausplan "$APP_DIR"
  chmod 600 "$APP_DIR/.env"
  echo ">>> Bitte DATABASE_URL in $APP_DIR/.env eintragen und das Skript erneut starten."
  exit 0
fi
chown -R hausplan:hausplan "$APP_DIR"

# Datenbankschema erstellen bzw. aktualisieren (Flask-Migrate / Alembic)
cd "$APP_DIR"
runuser -u hausplan -- "$APP_DIR/venv/bin/flask" db upgrade

install -m 644 deploy/hausplan.service /etc/systemd/system/hausplan.service
install -m 644 deploy/nginx-hausplan.conf /etc/nginx/sites-available/hausplan
ln -sf /etc/nginx/sites-available/hausplan /etc/nginx/sites-enabled/hausplan
rm -f /etc/nginx/sites-enabled/default

systemctl daemon-reload
systemctl enable --now hausplan
systemctl restart hausplan
nginx -t && systemctl reload nginx

echo "Fertig. Test im LAN:  curl -I http://$(hostname -I | awk '{print $1}')/auth/login"
echo "Demo-Daten (einmalig): cd $APP_DIR && runuser -u hausplan -- venv/bin/flask seed"

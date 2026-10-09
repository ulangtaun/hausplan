#!/usr/bin/env bash
# Neue Version ausrollen:  bash /opt/hausplan/deploy/update_app.sh
set -euo pipefail
cd /opt/hausplan
runuser -u hausplan -- git pull --ff-only
runuser -u hausplan -- venv/bin/pip install -r requirements.txt
runuser -u hausplan -- venv/bin/flask db upgrade
systemctl restart hausplan
echo "Update abgeschlossen."

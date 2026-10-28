#!/usr/bin/env bash
# Release-based backend update for the existing /opt/tracepilot installation.
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo 'Run as root' >&2; exit 1; }
source_dir="${1:?Source directory required}"
revision="${2:?Commit SHA required}"
[[ "$revision" =~ ^[0-9a-f]{40}$ ]] || exit 2
app=/opt/tracepilot
unit=/etc/systemd/system/tracepilot.service
[ -f "$app/.env" ] && [ -f "$unit" ] || { echo 'Bootstrap this server with deploy/setup.sh first.' >&2; exit 1; }
[ -f "$source_dir/backend/requirements.txt" ] && [ -f "$source_dir/backend/app/main.py" ] || exit 2
id tracepilot >/dev/null
mkdir -p "$app/releases" "$app/runs" "$app/deploy-backups"
chmod 700 "$app/deploy-backups"
release=$(mktemp -d "$app/releases/$revision.XXXXXX")
previous=$(readlink "$app/current" || true)
[ ! -e "$app/current" ] || [ -L "$app/current" ] || { echo 'current must be a symlink' >&2; exit 1; }
backup="$app/deploy-backups/$(date -u +%Y%m%dT%H%M%SZ)-$revision.service"
cp -p "$unit" "$backup"
switched=false
rollback() {
  status=$?
  trap - EXIT
  rm -f "$app/runs/.deployment-draining"
  if [ "$status" -ne 0 ] && [ "$switched" = true ]; then
    echo 'Health verification failed; restoring the preceding service configuration.' >&2
    if [ -n "$previous" ]; then
      ln -s "$previous" "$app/.rollback.$$"
      mv -Tf "$app/.rollback.$$" "$app/current"
    else
      rm -f "$app/current"
    fi
    cp -p "$backup" "$unit"
    systemctl daemon-reload
    systemctl restart tracepilot || true
  fi
  exit "$status"
}
trap rollback EXIT
rsync -a --exclude .git --exclude .github --exclude .env --exclude .venv \
  --exclude runs --exclude frontend --exclude node_modules "$source_dir/" "$release/"
ln -s "$app/.env" "$release/.env"
ln -s "$app/runs" "$release/runs"
chown -R tracepilot:tracepilot "$release"
chmod 750 "$release"
sudo -u tracepilot python3 -m venv "$release/.venv"
sudo -u tracepilot "$release/.venv/bin/pip" install --disable-pip-version-check -q -r "$release/backend/requirements.txt"
sudo -u tracepilot env PYTHONPATH="$release/backend" "$release/.venv/bin/python" -c 'from app.main import app; print("API import checks passed")'
sudo -u tracepilot docker build -q -t tracepilot-sandbox:1 "$release/sandbox" >/dev/null
# Do not terminate active investigations during a routine deployment.
touch "$app/runs/.deployment-draining"
deadline=$((SECONDS + 180))
while systemctl is-active --quiet tracepilot; do
  active=$(curl --max-time 5 -fsS http://127.0.0.1:8000/health | "$release/.venv/bin/python" -c 'import json,sys; print(json.load(sys.stdin).get("active_investigations", 1))')
  [ "$active" = 0 ] && break
  [ "$SECONDS" -lt "$deadline" ] || { echo 'Investigations are still active; deploy again when they finish.' >&2; exit 1; }
  sleep 5
done
# SQLite online backup captures accounts, sessions, settings and audit history without truncating data.
env APP_ROOT="$app" BACKUP_DIR="$app/deploy-backups" REVISION="$revision" "$release/.venv/bin/python" - <<'PY'
import os, sqlite3, time
from pathlib import Path
from dotenv import load_dotenv
root = Path(os.environ['APP_ROOT'])
load_dotenv(root / '.env')
path = Path(os.environ.get('TRACEPILOT_ADMIN_DB', str(root / 'runs/admin.sqlite3')))
if not path.is_absolute():
    path = root / path
if path.exists():
    destination = Path(os.environ['BACKUP_DIR']) / f"accounts-{int(time.time())}-{os.environ['REVISION']}.sqlite3"
    with sqlite3.connect(path) as source, sqlite3.connect(destination) as backup:
        source.backup(backup)
    destination.chmod(0o600)
PY
cat > "$app/.service.new.$$" <<EOF
[Unit]
Description=TracePilot AI API
After=network-online.target docker.service
Requires=docker.service

[Service]
User=tracepilot
WorkingDirectory=$app/current
EnvironmentFile=$app/.env
Environment=TRACEPILOT_RELEASE=$revision
ExecStart=$app/current/.venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
ln -s "$release" "$app/.current.new.$$"
mv -Tf "$app/.current.new.$$" "$app/current"
switched=true
install -o root -g root -m 644 "$app/.service.new.$$" "$unit"
rm -f "$app/.service.new.$$"
systemctl daemon-reload
systemctl restart tracepilot
for attempt in $(seq 1 30); do
  if curl --max-time 3 -fsS http://127.0.0.1:8000/health 2>/dev/null | \
    env REVISION="$revision" "$release/.venv/bin/python" -c 'import json,os,sys; d=json.load(sys.stdin); sys.exit(0 if d.get("status")=="ok" and d.get("release")==os.environ["REVISION"] else 1)' 2>/dev/null; then
    systemctl is-active --quiet tracepilot
    echo "Deployment healthy: $revision"
    exit 0
  fi
  sleep 2
done
echo 'The new release did not pass health and revision checks.' >&2
exit 1

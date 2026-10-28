#!/usr/bin/env bash
# Set up the TracePilot AI backend on a fresh Ubuntu 22.04/24.04 VM, behind HTTPS.
#
#   git clone https://github.com/SamppurnaTH/tracepilot-ai.git && cd tracepilot-ai
#   sudo bash deploy/setup.sh                 # HTTPS on <public-ip>.sslip.io
#   sudo DOMAIN=api.example.com bash deploy/setup.sh
#
# Safe to re-run: it updates the code, dependencies and service, and keeps .env.
set -euo pipefail

[ "$(id -u)" -eq 0 ] || { echo "Run with sudo." >&2; exit 1; }
SRC="$(cd "$(dirname "$0")/.." && pwd)"
APP=/opt/tracepilot
SITE="${SITE_ORIGIN:-https://tracepilot-ai.vercel.app}"

echo "==> Packages: Docker, Python, Caddy"
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq docker.io python3-venv python3-pip git caddy openssl curl rsync >/dev/null
systemctl enable --now docker >/dev/null

echo "==> Service user and code in $APP"
id tracepilot >/dev/null 2>&1 || useradd --system --create-home --shell /usr/sbin/nologin tracepilot
usermod -aG docker tracepilot
mkdir -p "$APP"
rsync -a --delete --exclude .git --exclude .env --exclude .venv --exclude runs --exclude frontend --exclude node_modules "$SRC/" "$APP/"
python3 -m venv "$APP/.venv"
"$APP/.venv/bin/pip" install -q --upgrade pip
"$APP/.venv/bin/pip" install -q -r "$APP/backend/requirements.txt"
mkdir -p "$APP/runs"

echo "==> Configuration ($APP/.env)"
ENV="$APP/.env"
[ -f "$ENV" ] || cp "$APP/.env.example" "$ENV"
[ -z "$(tail -c1 "$ENV")" ] || echo >> "$ENV"
setvar() { grep -q "^$1=" "$ENV" || echo "$1=$2" >> "$ENV"; }
setvar TRACEPILOT_CORS_ORIGINS "$SITE"
setvar TRACEPILOT_MAX_CONCURRENT 2
setvar TRACEPILOT_DAILY_LIMIT 40
setvar TRACEPILOT_REQUIRE_DOCKER 1
setvar TRACEPILOT_UPLOAD_KEY "$(openssl rand -hex 12)"
chown -R tracepilot:tracepilot "$APP"
chmod 600 "$ENV"

echo "==> Sandbox image (first build takes a few minutes)"
sudo -u tracepilot bash -c "cd $APP/backend && $APP/.venv/bin/python -c 'from app.sandbox import ensure_image; ensure_image()'"

echo "==> API service"
cat > /etc/systemd/system/tracepilot.service <<EOF
[Unit]
Description=TracePilot AI API
After=network-online.target docker.service
Requires=docker.service

[Service]
User=tracepilot
WorkingDirectory=$APP
EnvironmentFile=$ENV
ExecStart=$APP/.venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable tracepilot >/dev/null
systemctl restart tracepilot

echo "==> HTTPS"
if [ -z "${DOMAIN:-}" ]; then
  IP="$(curl -fsS https://checkip.amazonaws.com | tr -d '[:space:]')"
  DOMAIN="${IP//./-}.sslip.io"
fi
cat > /etc/caddy/Caddyfile <<EOF
$DOMAIN {
	reverse_proxy 127.0.0.1:8000 {
		flush_interval -1
	}
}
EOF
systemctl reload caddy || systemctl restart caddy

echo
echo "Backend: https://$DOMAIN"
if grep -q "^MODEL_API_KEY=$" "$ENV" || ! grep -q "^MODEL_API_KEY=." "$ENV"; then
  echo "Next: add your model keys:  sudo nano $ENV   then  sudo systemctl restart tracepilot"
fi
echo "Upload access key for judges: sudo grep TRACEPILOT_UPLOAD_KEY $ENV"
echo "Then set NEXT_PUBLIC_API_URL=https://$DOMAIN on Vercel and redeploy."

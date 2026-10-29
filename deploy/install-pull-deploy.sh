#!/usr/bin/env bash
# One-time setup on a server installed with deploy/setup.sh: from now on it deploys every commit on
# main whose CI passed, within a few minutes.
#
#   cd ~/tracepilot-ai && git pull && sudo bash deploy/install-pull-deploy.sh
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo 'Run with sudo.' >&2; exit 1; }
[ -f /opt/tracepilot/.env ] || { echo 'Run deploy/setup.sh on this server first.' >&2; exit 1; }
src="$(cd "$(dirname "$0")" && pwd)"

install -o root -g root -m 755 "$src/receive-deploy.sh" /usr/local/sbin/tracepilot-receive-deploy
install -o root -g root -m 755 "$src/pull-deploy.sh" /usr/local/sbin/tracepilot-pull-deploy

cat > /etc/systemd/system/tracepilot-pull-deploy.service <<'EOF'
[Unit]
Description=Deploy the newest TracePilot commit that passed CI
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/tracepilot-pull-deploy
TimeoutStartSec=30min
EOF

cat > /etc/systemd/system/tracepilot-pull-deploy.timer <<'EOF'
[Unit]
Description=Check GitHub for a new tested TracePilot commit

[Timer]
OnBootSec=2min
OnUnitInactiveSec=2min
RandomizedDelaySec=20s

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now tracepilot-pull-deploy.timer
systemctl start tracepilot-pull-deploy.service --no-block
echo 'Automatic deployment is on. Follow it with: journalctl -u tracepilot-pull-deploy -f'

#!/usr/bin/env bash
# One-time receiver installation. Invoked by the manually dispatched GitHub workflow.
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo 'Run as root' >&2; exit 1; }
revision="${1:-}"
deploy_user="${2:-}"
public_key="${3:-}"
[[ "$revision" =~ ^[0-9a-f]{40}$ ]] || exit 2
[[ "$deploy_user" =~ ^[a-z_][a-z0-9_-]*$ ]] || exit 2
[[ "$public_key" =~ ^ssh-ed25519\ [A-Za-z0-9+/=]+(\ [A-Za-z0-9._-]+)?$ ]] || exit 2
getent passwd "$deploy_user" >/dev/null
[ -f /opt/tracepilot/.env ] || { echo 'Run deploy/setup.sh on this instance before enabling CI/CD.' >&2; exit 1; }
work=$(mktemp -d /tmp/tracepilot-bootstrap.XXXXXX)
trap 'rm -rf "$work"' EXIT
curl --proto '=https' --tlsv1.2 --retry 3 -fsSL "https://codeload.github.com/SamppurnaTH/tracepilot-ai/tar.gz/$revision" -o "$work/source.tgz"
tar -xzf "$work/source.tgz" --strip-components=1 --no-same-owner -C "$work"
install -o root -g root -m 755 "$work/deploy/receive-deploy.sh" /usr/local/sbin/tracepilot-receive-deploy
home=$(getent passwd "$deploy_user" | cut -d: -f6)
install -d -m 700 -o "$deploy_user" -g "$(id -gn "$deploy_user")" "$home/.ssh"
authorized="$home/.ssh/authorized_keys"
touch "$authorized"
# No shell, forwarding, PTY or agent access. The sole argument is a validated commit SHA.
entry='restrict,command="sudo -n /usr/local/sbin/tracepilot-receive-deploy \"$SSH_ORIGINAL_COMMAND\"" '"$public_key"
grep -Fq "$public_key" "$authorized" || printf '%s\n' "$entry" >> "$authorized"
chown "$deploy_user:$(id -gn "$deploy_user")" "$authorized"
chmod 600 "$authorized"
printf '%s ALL=(root) NOPASSWD: /usr/local/sbin/tracepilot-receive-deploy *\n' "$deploy_user" > "$work/sudoers"
visudo -cf "$work/sudoers"
install -o root -g root -m 440 "$work/sudoers" /etc/sudoers.d/tracepilot-deploy
echo 'Restricted deployment receiver installed; existing SSH keys and application data preserved.'

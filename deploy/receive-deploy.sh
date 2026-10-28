#!/usr/bin/env bash
# Root-owned, forced SSH command. Only main's current immutable revision is deployable.
set -euo pipefail
revision="${1:-}"
[[ "$revision" =~ ^[0-9a-f]{40}$ ]] || { echo 'Expected a full commit SHA, not a shell command.' >&2; exit 2; }
exec 9>/var/lock/tracepilot-deployment.lock
flock -n 9 || { echo 'A deployment is already running.' >&2; exit 1; }
latest=$(git ls-remote https://github.com/SamppurnaTH/tracepilot-ai.git refs/heads/main | cut -f1)
[ "$revision" = "$latest" ] || { echo 'Refusing to deploy a revision superseded on main.' >&2; exit 1; }
work=$(mktemp -d /tmp/tracepilot-deploy.XXXXXX)
trap 'rm -rf "$work"' EXIT
curl --proto '=https' --tlsv1.2 --retry 3 -fsSL "https://codeload.github.com/SamppurnaTH/tracepilot-ai/tar.gz/$revision" -o "$work/source.tgz"
tar -xzf "$work/source.tgz" --strip-components=1 --no-same-owner -C "$work"
bash "$work/deploy/update.sh" "$work" "$revision"

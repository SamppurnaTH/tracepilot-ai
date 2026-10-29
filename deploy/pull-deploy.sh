#!/usr/bin/env bash
# Root-owned, run every few minutes by tracepilot-pull-deploy.timer. Deploys the newest commit on main
# once its CI run has passed. The server only makes outbound HTTPS requests: no inbound SSH, and no
# keys or cloud credentials stored in GitHub.
set -euo pipefail
repo=SamppurnaTH/tracepilot-ai
deployed=/opt/tracepilot/.deployed-revision
skipped=/opt/tracepilot/.skipped-revision

latest=$(git ls-remote "https://github.com/$repo.git" refs/heads/main | cut -f1)
[[ "$latest" =~ ^[0-9a-f]{40}$ ]] || { echo 'Could not read the main branch.' >&2; exit 1; }
[ "$(cat "$deployed" 2>/dev/null)" = "$latest" ] && exit 0
[ "$(cat "$skipped" 2>/dev/null)" = "$latest" ] && exit 0

# The public API allows 60 unauthenticated requests an hour; this runs only while main is ahead of the server.
state=$(curl --proto '=https' -fsS --max-time 20 -H 'Accept: application/vnd.github+json' \
  "https://api.github.com/repos/$repo/actions/workflows/ci-deploy.yml/runs?head_sha=$latest&event=push&per_page=1" |
  python3 -c 'import json,sys; r=json.load(sys.stdin).get("workflow_runs") or []; print(r[0]["status"] + ":" + str(r[0]["conclusion"]) if r else "none")')
case "$state" in
  completed:success) ;;
  completed:*)
    echo "CI did not pass for $latest ($state); not deploying it."
    echo "$latest" > "$skipped"
    exit 0 ;;
  *)
    echo "CI for $latest has not finished ($state); checking again shortly."
    exit 0 ;;
esac

/usr/local/sbin/tracepilot-receive-deploy "$latest"
echo "$latest" > "$deployed"

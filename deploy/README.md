# GitHub Actions → EC2

The Next.js frontend remains on Vercel. The FastAPI backend runs on the existing Ubuntu EC2 instance as `tracepilot.service`, behind Caddy HTTPS.

## Automatic delivery

`.github/workflows/ci-deploy.yml` runs on pull requests and pushes to `main`:

1. Run the complete Python test suite, including sandbox isolation, authorization and account migration checks.
2. Run `npm ci`, lint, TypeScript validation and a production Next.js build.

The server deploys itself. Every two minutes `tracepilot-pull-deploy.timer` runs `deploy/pull-deploy.sh`, which:

1. Reads the newest commit on `main` and stops if it is already deployed.
2. Asks the GitHub API whether CI passed for that commit. Still running: check again later. Failed: never deploy it.
3. Hands the commit to `deploy/receive-deploy.sh`, which downloads that exact revision and runs `deploy/update.sh` (see below).

The instance only makes outbound HTTPS requests. SSH stays restricted to your own IP, and GitHub holds no SSH keys, AWS credentials or model keys. Superseded commits are skipped automatically: only the newest commit on `main` is ever deployed.

## One-time setup on an existing server

The instance must already have `/opt/tracepilot/.env`, Docker, Python, rsync and the `tracepilot` service from `deploy/setup.sh`. Then:

```bash
cd ~/tracepilot-ai && git pull && sudo bash deploy/install-pull-deploy.sh
journalctl -u tracepilot-pull-deploy -f
```

The first check deploys the current `main` if its CI passed, converting the server to the release layout below. After that, do not re-run `deploy/setup.sh` for routine updates: it would point the service back at the pre-release layout. A merge to `main` is live on EC2 within about two minutes of CI passing.

## Release behavior

`deploy/receive-deploy.sh` accepts only a full SHA matching the current `main` revision in this repository. It downloads that immutable source archive and calls `deploy/update.sh`.

Each update creates a new release under `/opt/tracepilot/releases/`, installs its Python dependencies, checks API imports and builds the sandbox image. It links the release to the existing `/opt/tracepilot/.env` and `/opt/tracepilot/runs`; model keys, accounts, settings, audit history and saved investigations remain on the server.

Before restarting, deployments wait up to three minutes for active investigations to finish. Releases with the drain guard reject new investigation starts during that window. SQLite account databases and the preceding service unit are backed up under `/opt/tracepilot/deploy-backups/`. These backups are private to root.

The service switches through `/opt/tracepilot/current`. Deployment succeeds only when `/health` returns `status=ok` and `release=<the tested SHA>`. If verification fails, the preceding symlink and service unit are restored. Database backups are retained for deliberate recovery; they are not automatically restored over newer data. Releases are retained for review and rollback; monitor disk space and remove unused releases deliberately.

The application and its credentials are not copied from the developer's computer during deployment.

## Fresh instance bootstrap

On Ubuntu 22.04/24.04, clone this repository and run:

```bash
sudo DOMAIN=api.example.com SITE_ORIGIN=https://tracepilot-ai.vercel.app bash deploy/setup.sh
sudo nano /opt/tracepilot/.env
sudo systemctl restart tracepilot
```

Configure model credentials and the first administrator using `TRACEPILOT_ADMIN_EMAIL` and `TRACEPILOT_ADMIN_PASSWORD` (at least 12 characters). Existing account databases are preserved. Caddy terminates HTTPS; the API binds only to `127.0.0.1:8000`.

Set `NEXT_PUBLIC_API_URL=https://api.example.com` in Vercel Production before rebuilding the frontend. Vercel's connected Git integration handles frontend delivery separately from the EC2 backend workflow.

## Operations

```bash
sudo systemctl status tracepilot
sudo journalctl -u tracepilot -n 100 --no-pager
curl -fsS http://127.0.0.1:8000/health
readlink /opt/tracepilot/current
```

Runtime limits, required Docker isolation, upload access keys and CORS allowlists stay in `/opt/tracepilot/.env`. Routine CI/CD updates preserve Caddy configuration and these values.

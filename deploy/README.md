# GitHub Actions → EC2

The Next.js frontend remains on Vercel. The FastAPI backend runs on the existing Ubuntu EC2 instance as `tracepilot.service`, behind Caddy HTTPS.

## Automatic delivery

`.github/workflows/ci-deploy.yml` runs on pull requests and pushes to `main`:

1. Run the complete Python test suite, including sandbox isolation, authorization and account migration checks.
2. Run `npm ci`, lint, TypeScript validation and a production Next.js build.
3. On `main`, deploy that exact commit only when both jobs pass and `EC2_DEPLOY_ENABLED=true`.
4. Ignore superseded commits and serialize deployments to the production environment.

GitHub-hosted runners connect to EC2. No local AWS CLI credentials or local EC2 connection is needed for subsequent deployments. The instance must accept SSH from the runner; do not disable host-key verification or open SSH publicly just to make a job pass. For a server with private SSH access, use an approved runner with access to that network or configure AWS Systems Manager instead.

### Repository variables

| Variable | Purpose |
| --- | --- |
| `EC2_HOST` | EC2 public DNS name or IP |
| `EC2_USER` | Existing SSH user, normally `ubuntu` for this Ubuntu installation |
| `EC2_PORT` | SSH port; defaults to `22` |
| `EC2_DEPLOY_PUBLIC_KEY` | Public half of the dedicated deployment key |
| `EC2_DEPLOY_ENABLED` | Set to `true` only after successful bootstrap and host-key pinning |
| `NEXT_PUBLIC_API_URL` | Optional API URL for the CI frontend build; set the production value separately on Vercel |

### Environment secrets

Use the `ec2-production` GitHub environment, restricted to the `main` branch.

| Secret | Purpose |
| --- | --- |
| `EC2_SSH_PRIVATE_KEY` | Dedicated deployment key. Its public key is installed with a forced deployment command: no shell, PTY or port forwarding. |
| `EC2_KNOWN_HOSTS` | Pinned SSH host-key entry, obtained during the one-time bootstrap |
| `EC2_BOOTSTRAP_KEY` | Existing instance key, temporarily used for bootstrap. Delete it when bootstrap is finished, including if setup is abandoned. |

Never commit private keys, model credentials, account databases or `.env` files.

## One-time setup on an existing server

The instance must already have `/opt/tracepilot/.env`, Docker, Python, rsync, and the `tracepilot` service from `deploy/setup.sh`.

1. Set the repository variables and the two private-key secrets described above. Keep `EC2_DEPLOY_ENABLED=false`.
2. Run **Actions → Bootstrap EC2 deployment access → Run workflow** on `main`.
3. The runner installs the root-owned deployment receiver and the restricted public key, preserving existing SSH keys. The first connection uses trust on first use for the specified host; all routine deployments require the pinned host key.
4. Store the host-key entry printed between `EC2_HOST_KEY_BEGIN` and `EC2_HOST_KEY_END` as `EC2_KNOWN_HOSTS` in the production environment. Verify the fingerprint using the instance's existing trusted console connection when available.
5. Delete `EC2_BOOTSTRAP_KEY` and set `EC2_DEPLOY_ENABLED=true`.
6. Run **CI and EC2 deployment** manually, or push the next change to `main`.

If SSH times out, fix runner-to-instance network access before retrying. A successful CI build alone does not mean the EC2 service has been updated. The deployment job must finish successfully.

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

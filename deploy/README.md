# Hosting the backend

The site on Vercel is static. Live runs need the FastAPI backend somewhere that can start Docker containers, because every investigation runs in a sandbox. This sets that up on a single Linux VM, behind HTTPS.

## 1. Create a VM

- Ubuntu 24.04 (or 22.04), **2 vCPU, 4 GB RAM, 30 GB disk**. Java projects build with Maven, which needs the memory.
  For example, an AWS EC2 `t3.medium` costs about $1 a day; a DigitalOcean 4 GB droplet costs about $24 a month.
- Open inbound ports **22** (SSH), **80** and **443**.

## 2. Install

```bash
git clone https://github.com/SamppurnaTH/tracepilot-ai.git && cd tracepilot-ai
sudo bash deploy/setup.sh
```

This installs Docker, Python and Caddy, runs the API as a `tracepilot` service on `127.0.0.1:8000`, and serves it over HTTPS at `https://<public-ip-with-dashes>.sslip.io` (a free hostname that points at the IP, with a Let's Encrypt certificate). Pass `DOMAIN=api.example.com` to use your own domain. Re-run the script to deploy new code.

## 3. Add the model keys

```bash
sudo nano /opt/tracepilot/.env      # MODEL_API_KEY, and BASETEN_API_KEY for the reviewer
sudo systemctl restart tracepilot
curl https://<your-host>/health
```

## 4. Point the site at it

On Vercel, set `NEXT_PUBLIC_API_URL=https://<your-host>` for Production and redeploy. The sidebar then reads "Live backend connected", and example scenarios run live.

## Guards for a public server

Set in `/opt/tracepilot/.env` (the script writes these defaults):

| Variable | Default | What it does |
| --- | --- | --- |
| `TRACEPILOT_CORS_ORIGINS` | `https://tracepilot-ai.vercel.app` | Sites allowed to call the API from a browser |
| `TRACEPILOT_MAX_CONCURRENT` | `2` | Investigations running at once |
| `TRACEPILOT_DAILY_LIMIT` | `40` | Live runs per UTC day, to cap model spend (`0` = no limit) |
| `TRACEPILOT_UPLOAD_KEY` | random | Needed to investigate an uploaded ZIP or a repository URL; the examples run without it. Read it with `sudo grep UPLOAD_KEY /opt/tracepilot/.env` |
| `TRACEPILOT_REQUIRE_DOCKER` | `1` | Refuse to run instead of falling back to process isolation |

Logs: `journalctl -u tracepilot -f`. Saved runs: `/opt/tracepilot/runs`.

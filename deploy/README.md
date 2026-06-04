# Self-host deployment (run the full app at your own domain)

This runs the **whole application** — MySQL, the Playwright-enabled backend, and
the built frontend, behind Caddy with automatic HTTPS — on a server you control,
reachable at your domain (for example `https://yourdomain.com`, with the API at
`https://api.yourdomain.com`).

Read this first: the app's "Connect Kaggle Account" button logs whoever clicks it
in **as you**, using your saved Kaggle session (`auth.json`). That is fine for a
site only *you* use. Do not advertise the URL as a public service — keep it
access-controlled (see "Lock it down" below). A server openly scraping Kaggle on
behalf of strangers risks getting your Kaggle account banned.

## What you need

- A small Linux VPS (Ubuntu 22.04+ is fine). Give it at least 2 GB RAM — the
  backend runs a headless Chromium via Playwright, which is memory-hungry.
- A domain you own, with DNS you can edit.
- Docker and the Docker Compose plugin on the server.
- Your `auth.json` (generated locally — see step 4). The interactive Kaggle
  login opens a browser, so it cannot be produced on a headless server.

## DNS

Point two records at your server's public IP:

| Type | Name | Value |
|------|------|-------|
| A | `yourdomain.com` (apex / `@`) | your server IP |
| A | `api.yourdomain.com` (`api`) | your server IP |

Caddy will obtain HTTPS certificates for both automatically once these resolve.

## Steps

1. **Install Docker on the server** (if needed):

   ```bash
   curl -fsSL https://get.docker.com | sh
   ```

2. **Clone the repository** on the server:

   ```bash
   git clone https://github.com/AsutoshaNanda/kaggle-replays.git
   cd kaggle-replays/deploy
   ```

3. **Configure environment**:

   ```bash
   cp .env.example .env
   # Edit .env: set DOMAIN, the MySQL passwords, and the two JWT secrets.
   ```

4. **Provide your Kaggle session.** On your *local* machine, generate it and copy
   it to the server next to the compose file:

   ```bash
   # locally, in the repo's Backend/ directory:
   .venv/bin/python login.py            # log in to Kaggle, then close the browser -> auth.json
   scp Backend/auth.json   user@your-server:/path/to/kaggle-replays/deploy/auth.json
   ```

5. **Launch** (from `deploy/` on the server):

   ```bash
   docker compose up -d --build
   ```

   The backend applies migrations on startup; Caddy provisions HTTPS within a
   minute or two. Then open `https://yourdomain.com` and click "Connect Kaggle
   Account".

6. **Lock it down.** Edit `deploy/Caddyfile`, uncomment the IP-allowlist block in
   *both* site sections with your IP (from https://ifconfig.me), then:

   ```bash
   docker compose restart caddy
   ```

   Alternatives noted in the Caddyfile: HTTP basic auth, or front the whole thing
   with a VPN / Cloudflare Access.

## Operating it

- **Logs:** `docker compose logs -f backend` (or `caddy`, `frontend`, `db`).
- **Update to the latest code:** `git pull && docker compose up -d --build`.
- **Data persistence:** MySQL data, downloads, and Caddy's certificates live in
  named volumes, so they survive restarts.
- **Session expiry:** Kaggle sessions lapse periodically. When data stops loading
  or you see "session expired", regenerate `auth.json` locally (step 4), copy it
  over, and `docker compose restart backend`.
- **Playwright version:** the backend image installs the latest Playwright plus
  Chromium. If `downloader.py` ever needs a specific version, pin it in
  `Dockerfile.backend`.

## Why not a one-click PaaS?

Render, Railway, Fly.io, etc. can host the backend and a managed MySQL, but this
app needs a long-running headless Chromium and a persistent `auth.json` /
sessions directory, which is awkward on platforms with ephemeral filesystems and
strict memory limits. A small VPS with Docker Compose (this setup) is the most
reliable. If you specifically want a PaaS recipe, that can be added.

## Reminder

This is for your own use. Keep it access-controlled, and remember it is bound by
Kaggle's Terms of Service — it uses Kaggle's internal API through your personal
session.

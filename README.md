# Kaggle Replays

A self-hosted tool for browsing, analyzing, and bulk-downloading the **episode
replays** from your Kaggle simulation competitions (for example "Game Arena"
style competitions such as Orbit Wars, Lux AI, Halite, and similar). It pairs a
FastAPI backend with a React single-page frontend and a MySQL cache, and it
talks to Kaggle through an authenticated browser session so you can do at scale
what the Kaggle website only lets you do one click at a time.

This document explains both **what** the project does and, more importantly,
**why it is built the way it is** — because most of the non-obvious design
decisions exist to avoid getting your Kaggle account rate-limited or banned.

---

## Table of contents

1. [Why this project exists](#why-this-project-exists)
2. [What it does](#what-it-does)
3. [How it works](#how-it-works)
4. [Architecture](#architecture)
5. [Technology stack](#technology-stack)
6. [Repository layout](#repository-layout)
7. [Prerequisites](#prerequisites)
8. [Setup and run](#setup-and-run)
9. [Using the application](#using-the-application)
10. [Data freshness and the rate-limit-safe design](#data-freshness-and-the-rate-limit-safe-design)
11. [Configuration reference](#configuration-reference)
12. [Security model and deployment warning](#security-model-and-deployment-warning)
13. [API reference](#api-reference)
14. [Development](#development)
15. [Troubleshooting](#troubleshooting)
16. [Limitations and responsible use](#limitations-and-responsible-use)
17. [License](#license)

---

## Why this project exists

Kaggle simulation competitions produce **episodes**: individual matches your
submitted agent plays against others. Each episode has a downloadable **replay**
(a JSON document describing every step of the match) and an outcome (win, loss,
or draw) derived from the agents' terminal rewards. Studying these replays is
one of the best ways to improve an agent, but the Kaggle web interface only
exposes them one at a time, behind a paginated UI, with no bulk export and no
easy way to filter "show me only the games I lost".

Doing this manually is slow and tedious. Automating it naively is dangerous:
Kaggle's internal API rate-limits aggressively, and hammering it in a loop can
get your account temporarily throttled or, in the worst case, banned. The entire
point of this project is to make replay collection and analysis **convenient and
safe**:

- Convenient: one screen to browse competitions, submissions, and per-submission
  episodes; bulk download with outcome filtering; a leaderboard view; and a
  "top 10 percent" daily snapshot view.
- Safe: every read the user interface performs is served from a local database
  cache. The live Kaggle API is only touched on a schedule or when you
  explicitly press "Sync now" — never automatically on page loads or navigation.

## What it does

- Lists the competitions you have entered, with status (active or completed).
- Lists your submissions for a competition, with the real score (see
  ["scores"](#how-scores-are-determined) below) and episode count.
- Lists the episodes for a submission with a computed outcome (win, loss, draw)
  and lets you bulk-download their replays as JSON or ZIP, optionally filtered by
  outcome.
- Shows the current public leaderboard for a competition (rank, team, score,
  medal) with a top-ten-percent cutoff.
- Reconstructs and stores daily leaderboard snapshots ("Top 10 percent Replays")
  so you can see how the top performers and their replay episode IDs changed over
  time.
- Streams live download progress over a WebSocket.
- Presents a read-only profile panel sourced from your Kaggle session.

## How it works

### The authentication model: a real browser session, not an API key

Kaggle does not offer a public API for simulation episodes and replays. The data
the app needs is served by Kaggle's **internal** API (the same endpoints the
Kaggle website calls in your browser). Those endpoints require a logged-in
session and a CSRF token that lives in your browser cookies.

To reach them, the backend drives a **Playwright** browser context that is
already authenticated. You log in to Kaggle once in a real browser window; that
session is saved to `auth.json`. The backend then reuses that saved session to
call the internal endpoints exactly as the website would, reading the
`XSRF-TOKEN` and build-hash cookies at runtime.

Two consequences follow directly from this model, and they shape everything
else:

1. **`auth.json` is a live credential.** Anyone who has it can act as you on
   Kaggle. It is never committed, never logged, and stored with `0600`
   permissions. See [Security model](#security-model-and-deployment-warning).
2. **This is fundamentally a single-user, local tool.** There is no public
   Kaggle OAuth to plug in; the app acts as *you*. Running it as a public,
   multi-user website would mean putting your personal Kaggle session on a
   server, which you should not do.

For convenient local use there is a `DEV_LOGIN_ENABLED` flag. When set, the
frontend's "Connect Kaggle Account" button logs you in using the local
`auth.json` produced by `login.py`, with no token juggling.

### The data flow

```
Kaggle internal API  ──(Playwright session)──►  Backend services
                                                      │
                                       writes to      ▼
                                                 MySQL cache
                                                      │
                                       reads from     ▼
   Browser (React SPA)  ◄────────(REST + WebSocket)────  FastAPI routers
```

- `competitions` -> `submissions` -> `episodes` -> `replays` is the natural
  drill-down. Each level is fetched from Kaggle once, written to MySQL, and then
  served from MySQL on every subsequent view.
- Leaderboards are fetched via Kaggle's `GetLeaderboard` endpoint and stored as
  dated snapshots so history can be reconstructed and the top-ten-percent cutoff
  computed (`ceil(number_of_teams * 0.10)`).

### How scores are determined

In simulation competitions a submission's visible "score" (often a number in the
hundreds or low thousands) is the agent's **skill rating**, not a metric like
accuracy. Kaggle reports this rating inside the episode data
(`agents[].updatedScore`), not in the submission's `publicScoreFormatted` field
(which is typically `0` or empty for these competitions). The backend therefore
derives a submission's score from the most recent episode's skill rating for
that submission's agent, and treats a literal `0`/empty formatted score as
"unknown" rather than displaying a misleading `0`.

## Architecture

| Layer | Responsibility |
|-------|----------------|
| `Backend/downloader.py` | The original async Playwright module: the low-level functions that call Kaggle's internal API (list competitions / submissions / episodes, fetch replays in batches), classify episode outcomes from agent rewards, and package downloads. The web backend imports these functions directly rather than duplicating them. |
| `Backend/backend/` | The FastAPI application: routers, services, background workers, MySQL models, JWT auth, a security layer (transport headers, strict CORS, rate limiting, audit log, path-traversal guards), a per-user Playwright context pool, and a daily sync scheduler. |
| `Database/` | The MySQL schema snapshot and migration references. |
| `Frontend/` | The Vite + React + TypeScript single-page app (in-memory access token, WebSocket-driven live progress, light/dark themes). |

The backend keeps routers thin: HTTP concerns live in `routers/`, Kaggle and
persistence logic lives in `services/` and `tasks/`, and all database access goes
through the SQLAlchemy ORM (no raw SQL).

## Technology stack

- Backend: Python 3.12, FastAPI, SQLAlchemy 2 (async, aiomysql), Alembic,
  Playwright, python-jose (JWT), slowapi (rate limiting), structlog.
- Database: MySQL 8/9.
- Frontend: Vite 5, React 18, TypeScript 5 (strict), React Router 6, Axios,
  Zustand, Framer Motion, Tailwind CSS v4.

## Repository layout

```
.
├── Backend/
│   ├── downloader.py            # Phase 1: low-level Kaggle API + replay downloader (async)
│   ├── login.py                 # interactive Kaggle login -> writes auth.json
│   ├── inspect_*.py, test*.py   # exploratory scripts used to discover the internal API
│   └── backend/                 # the FastAPI application package
│       ├── main.py              # app factory + lifespan (starts the daily scheduler)
│       ├── config.py database.py models.py schemas.py security.py
│       ├── middleware.py dependencies.py audit.py logging_config.py
│       ├── session_manager.py   # per-user Playwright context pool (LRU)
│       ├── kaggle_service.py    # bridge to downloader.py + leaderboard/episode helpers
│       ├── routers/             # auth, competitions, submissions, downloads, ws, leaderboard
│       ├── services/            # auth_service, download_service, kaggle_data_service
│       ├── tasks/               # download_worker, leaderboard_worker (+ daily scheduler)
│       ├── utils/               # cache (TTL), file_utils, sanitize
│       ├── alembic/             # database migrations
│       └── .env.example         # configuration template (copy to .env)
├── Database/
│   ├── schema.sql               # schema snapshot
│   └── migrations_reference/
└── Frontend/
    ├── src/                     # pages, components, api client, auth, store, types
    ├── .env.example
    └── package.json
```

Secrets and per-user data (`auth.json`, `request.txt`, `*/.env`, `sessions/`,
`downloads/`, `logs/`, virtualenvs, `node_modules`) are excluded by
`.gitignore` and must never be committed.

## Prerequisites

- Python 3.12 and the ability to create a virtual environment.
- Node.js 18 or newer (for the frontend).
- MySQL 8 or 9, running locally.
- A Kaggle account that has entered at least one simulation competition.

## Setup and run

### 1. Database

```bash
# Start MySQL (Homebrew example)
brew services start mysql

# Create the database and an application user (adjust the password):
#   CREATE DATABASE kaggle_replays CHARACTER SET utf8mb4;
#   CREATE USER 'kr_app'@'localhost' IDENTIFIED BY 'YOUR_PASSWORD';
#   GRANT ALL PRIVILEGES ON kaggle_replays.* TO 'kr_app'@'localhost';
#   FLUSH PRIVILEGES;
```

See `Database/README.md` for details.

### 2. Backend configuration

```bash
cd Backend
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
.venv/bin/python -m playwright install chromium

cp backend/.env.example backend/.env
# Edit backend/.env:
#  - DATABASE_URL with your MySQL password
#  - JWT_SECRET and JWT_REFRESH_SECRET (two DIFFERENT 64-hex strings;
#      generate with: python -c "import secrets; print(secrets.token_hex(32))")
#  - set DEV_LOGIN_ENABLED=true for single-user local use
```

### 3. Create your Kaggle session

```bash
# Opens a browser; log in to Kaggle, then close the window. Writes auth.json.
.venv/bin/python login.py
```

Re-run this whenever the session expires (symptoms: empty data, or a "Kaggle
session expired" message).

### 4. Apply database migrations and start the API

```bash
# From the Backend directory:
.venv/bin/python -m alembic -c backend/alembic.ini upgrade head
.venv/bin/python -m uvicorn backend.main:app --reload --port 8000
```

Health check: `curl http://127.0.0.1:8000/health` returns `{"status":"ok"}`.
Interactive API docs: http://127.0.0.1:8000/docs

### 5. Frontend

```bash
cd Frontend
npm install
cp .env.example .env     # VITE_API_BASE_URL defaults to http://localhost:8000
npm run dev              # http://localhost:5173
```

Open http://localhost:5173 and press "Connect Kaggle Account".

## Using the application

1. **Home** lists your competitions. Open one to see its submissions.
2. **Submissions** shows each submission's score and episode count. Press
   **Sync now** to force a fresh pull from Kaggle (otherwise data is served from
   the local cache). A "Last synced" label shows how fresh the data is.
3. **Leaderboard** (sidebar or per competition) shows the current public
   standings and the top-ten-percent cutoff, with a competition selector and
   search.
4. **Top 10 percent Replays** shows dated leaderboard snapshots and the replay
   episode IDs for the top performers. Use **Backfill** to reconstruct history
   from your cached submissions; the daily scheduler captures real snapshots
   going forward.
5. From a submission you can bulk-download replays (JSON or ZIP), optionally
   filtered by outcome, and watch live progress.

## Data freshness and the rate-limit-safe design

This is the most important design decision in the project. The user interface
**never** calls Kaggle directly on a page load or a navigation. Instead:

- All reads come from the MySQL cache.
- The cache is refreshed in exactly two ways:
  1. A **daily scheduler** (a pure-asyncio loop in the backend) that, once per
     day, refreshes competitions, submissions, episode lists, scores, and
     leaderboard snapshots.
  2. A manual **Sync now** action you trigger yourself, which performs one batch
     refresh for a single competition.
- When cached data is older than the freshness window (24 hours by default), the
  app shows a "Last synced X ago" label but does **not** automatically re-fetch.
- Episode lookups that do hit Kaggle (the first time a submission is seen, or
  during a sync) are performed **sequentially with a short delay** and stop
  immediately on the first rate-limit response, leaving the rest to a later run.

The net effect: normal browsing is free of Kaggle traffic, and the only live
calls are paced and bounded. This is what keeps your account safe.

## Configuration reference

Backend (`Backend/backend/.env`, see `.env.example` for the annotated template):

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | Async SQLAlchemy URL (`mysql+aiomysql://user:pass@host:3306/kaggle_replays`). |
| `JWT_SECRET`, `JWT_REFRESH_SECRET` | Two different 64-hex signing secrets. |
| `ALLOWED_ORIGINS` | Comma-separated CORS allow-list (no wildcards). |
| `DEV_LOGIN_ENABLED` | `true` for single-user local login via `auth.json`. Leave false/unset otherwise. |
| `SESSIONS_BASE_DIR`, `DOWNLOADS_BASE_DIR` | Where per-user sessions and job output are written. |
| `MAX_CONCURRENT_CONTEXTS`, `MAX_PARALLEL_DOWNLOAD_JOBS`, `JOB_OUTPUT_TTL_HOURS` | Concurrency and cleanup tuning. |
| `LOG_LEVEL`, `LOG_FILE` | Logging. |

Frontend (`Frontend/.env`): `VITE_API_BASE_URL` (defaults to
`http://localhost:8000`).

## Security model and deployment warning

The backend ships with a deliberate security layer: JWT access tokens (15
minutes) with rotating refresh tokens delivered as httponly, secure,
SameSite=strict cookies; a per-user concurrent-session cap; transport-security
response headers; a strict CORS allow-list; slowapi rate limits with blocked
requests written to an audit log; Pydantic request bodies that reject unknown
fields; ORM-only database access; and path-traversal-guarded file operations.
The access token is held only in browser memory, never in local storage.

Despite all of this, please read the following carefully:

> **Do not deploy this as a public, multi-user website using your own Kaggle
> session.** The application authenticates to Kaggle as *you* via `auth.json`.
> Hosting it publicly would place your live Kaggle credentials on a server and
> expose your account to anyone who can reach it, and automated traffic against
> Kaggle's internal API may violate Kaggle's Terms of Service. This project is
> intended to run **locally, for your own account**. If you want a public
> presence for the project, publish a static landing/documentation page and
> keep the live application local. See the "hosting" discussion in the project
> notes.

`DEV_LOGIN_ENABLED` must be left false/unset in any non-local context.

## API reference

| Method | Path | Notes |
|--------|------|-------|
| POST | `/auth/kaggle-login`, `/auth/refresh`, `/auth/logout` | JWT; refresh rotates; rate limited |
| GET | `/auth/me` | current user (read-only profile) |
| GET | `/competitions`, `/competitions/{kaggleId}/submissions` | user-scoped, served from cache |
| POST | `/competitions/{kaggleId}/sync` | manual "Sync now": refresh submissions, episodes, scores, leaderboard |
| GET | `/submissions/{id}/episodes?filter=` | episode IDs + outcomes, served from cache |
| POST | `/downloads/start`, `/downloads/bulk` | background download jobs |
| GET | `/downloads`, `/downloads/{uuid}/status`, `/downloads/{uuid}/file` | history / progress / ZIP stream |
| WS | `/ws/downloads/{uuid}?token=` | live progress |
| GET | `/leaderboard/{kaggleId}/current`, `/leaderboard/{kaggleId}/history` | current standings / daily snapshots |
| POST | `/leaderboard/{kaggleId}/sync` | daily sync or historical backfill |

Note: leaderboard and submission routes both accept the **Kaggle numeric
competition id** (the value used throughout the frontend), and resolve the
internal record from it.

## Development

```bash
# Backend: byte-compile / import check
cd Backend && .venv/bin/python -c "import backend.main"

# Database migrations
.venv/bin/python -m alembic -c backend/alembic.ini history
.venv/bin/python -m alembic -c backend/alembic.ini upgrade head
.venv/bin/python -m alembic -c backend/alembic.ini downgrade -1

# Frontend: type-check + production build
cd Frontend && npm run build      # runs tsc -b && vite build
npm run dev                       # development server
```

## Troubleshooting

- **"Could not start the Kaggle login flow"** in the UI: the backend is not
  running, or the frontend is pointed at the wrong `VITE_API_BASE_URL`. Start the
  backend (step 4) and confirm `curl http://127.0.0.1:8000/health`.
- **Empty data or "Kaggle session expired"**: your `auth.json` lapsed. Re-run
  `python login.py`.
- **"Kaggle is rate-limiting requests (429)"**: Kaggle throttled a burst. Wait a
  few minutes; the app surfaces this clearly and will not record a throttled
  response as zero episodes. Prefer "Sync now" over repeated manual refreshes.
- **Scores show as a dash**: the skill rating has not been resolved yet. It fills
  in after the background episode resolve completes (or after a "Sync now").

## Limitations and responsible use

- This tool uses Kaggle's **internal** API through your own logged-in session. It
  is provided for personal, educational use with your own account and data.
  Respect Kaggle's Terms of Service, and do not use it to place undue load on
  Kaggle's services or to access data that is not yours.
- It targets simulation/episode competitions; predictive (metric-scored)
  competitions are only partially relevant (their scoring differs).
- It is single-user and local by design (see the security warning).

## License

No license file is included yet. Until a `LICENSE` is added, all rights are
reserved by the author. If you intend to open-source this publicly, add a
license (for example MIT or Apache-2.0) so others know how they may use it.

## Acknowledgements

Built on FastAPI, SQLAlchemy, Playwright, React, and Vite. "Kaggle" and the
Kaggle logo are trademarks of Kaggle/Google; this project is not affiliated with
or endorsed by Kaggle.

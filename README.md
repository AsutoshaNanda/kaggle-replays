# Kaggle Replays

Browse, view, and bulk-download the episode replays from your Kaggle simulation competitions, all from one local web app — with a data layer designed so you never get rate-limited or banned for collecting them.



This README is intentionally thorough. It documents not only how to run the project, but *why* it is built the way it is, and the real problems that shaped it — because almost every non-obvious decision here exists to work around Kaggle's internal API and its aggressive rate limiting.

## Table of contents

1. [What it does](#what-it-does)
2. [Why this project exists](#why-this-project-exists)
3. [Features](#features)
4. [Demo](#demo)
5. [How it works](#how-it-works)
   - [Authentication: a real browser session, not an API key](#authentication-a-real-browser-session-not-an-api-key)
   - [The data flow](#the-data-flow)
   - [How submission scores are determined](#how-submission-scores-are-determined)
   - [The rate-limit-safe design](#the-rate-limit-safe-design)
6. [Architecture](#architecture)
7. [Tech stack](#tech-stack)
8. [Repository layout](#repository-layout)
9. [Prerequisites](#prerequisites)
10. [Getting started](#getting-started)
11. [Environment variables](#environment-variables)
12. [Using the application](#using-the-application)
13. [Security model and deployment warning](#security-model-and-deployment-warning)
14. [API reference](#api-reference)
15. [Database migrations](#database-migrations)
16. [Development journey and issues faced](#development-journey-and-issues-faced)
17. [Troubleshooting](#troubleshooting)
18. [Limitations and responsible use](#limitations-and-responsible-use)
19. [Contributing](#contributing)
20. [License](#license)

## What it does

Kaggle simulation competitions (the "Game Arena" style competitions where you submit an agent that plays matches against others — Orbit Wars, Lux AI, Halite, and similar) generate large numbers of **episodes**: individual matches your agent played. Each episode has a downloadable **replay** (a JSON document describing every step of the match) and an outcome (win, loss, or draw). The Kaggle website only lets you reach these one at a time, with no bulk export and no way to filter by outcome.

Kaggle Replays is a self-hosted web app that gives you a single place to browse the competitions you have entered, inspect each submission and its episodes, filter those episodes by outcome, and download their replays in bulk for offline analysis. It also shows the live leaderboard and the daily top performers with their replay IDs, so you can study how the best agents are playing. It is for Kaggle competitors who want to analyze replays at scale.

## Why this project exists

Studying replays is one of the best ways to improve a competition agent, but doing it by hand is slow, and automating it naively is dangerous. Kaggle does not expose a public API for simulation episodes and replays, and the internal endpoints that serve that data rate-limit aggressively. A tight request loop returns `429 RESOURCE_EXHAUSTED` and can get your account temporarily throttled or, worst case, flagged. The entire project is organized around making replay collection both convenient and safe:

- Convenient: one screen for competitions, submissions, episodes (with outcomes), bulk download, leaderboard, and top-performer replays.
- Safe: every read the interface performs is served from a local database cache. The live Kaggle API is only touched on a schedule or when you explicitly press a sync button — never automatically on page loads or navigation.

## Features

- Browse the competitions you have entered, with active and completed status badges and tab filtering.
- View submissions for a competition, including each submission's real skill-rating score and episode count.
- List a submission's episodes with an automatically computed outcome (win, loss, or draw), derived from the agents' terminal rewards with zero extra fetches.
- Bulk-download replays as JSON or ZIP, optionally filtered by outcome, with live progress streamed over a WebSocket.
- View the current public leaderboard with a top-ten-percent cutoff, search, a "show all" toggle, and a competition selector.
- "Top 10% Replays": daily leaderboard snapshots and the replay episode IDs of the top performers, captured on demand or on a schedule.
- Read-only profile panel sourced from your Kaggle session, with a link out to Kaggle for edits.
- A rate-limit-safe data layer with "last synced X ago" labels and manual "Sync now" controls.
- Light and dark themes.
- [PASTE: add any additional features]

## Demo

[ADD SCREENSHOT OR GIF HERE]

## How it works

### Authentication: a real browser session, not an API key

Kaggle does not offer a public API for simulation episodes and replays. The data this app needs is served by Kaggle's **internal** API — the same endpoints the Kaggle website calls in your browser — which require a logged-in session and a CSRF token stored in browser cookies.

To reach them, the backend drives a **Playwright** browser context that is already authenticated. You log in to Kaggle once in a real browser window (`python login.py`); that session is saved to `auth.json`. The backend reuses that saved session to call the internal endpoints exactly as the website would, reading the `XSRF-TOKEN` and build-hash cookies at runtime. The identity of the logged-in user is read from the `CLIENT-TOKEN` cookie (a JWT whose payload contains the username, display name, avatar URL, profile URL, and tier).

Two consequences follow directly from this model and shape everything else:

1. **`auth.json` is a live credential.** Anyone who has it can act as you on Kaggle. It is never committed (it is gitignored), never logged, and stored with `0600` permissions.
2. **This is fundamentally a single-user, local tool.** There is no public Kaggle OAuth to plug in; the app acts as *you*. Running it as a public, multi-user website would mean putting your personal Kaggle session on a server, which you should not do.

For convenient local use there is a `DEV_LOGIN_ENABLED` flag. When set, the frontend's "Connect Kaggle Account" button logs you in using the local `auth.json`, with no token juggling. The app's own session uses JWT access tokens (15 minutes, held only in browser memory) and rotating refresh tokens delivered as httponly, secure, SameSite=strict cookies.

### The data flow

```
Kaggle internal API  --(Playwright session)-->  Backend services
                                                      |
                                       writes to      v
                                                 MySQL cache
                                                      |
                                       reads from     v
   Browser (React SPA)  <-------(REST + WebSocket)------  FastAPI routers
```

`competitions -> submissions -> episodes -> replays` is the natural drill-down. Each level is fetched from Kaggle once, written to MySQL, and then served from MySQL on every subsequent view. Leaderboards are fetched via Kaggle's `GetLeaderboard` endpoint and stored as dated snapshots so history can be reconstructed and the top-ten-percent cutoff computed as `ceil(number_of_teams * 0.10)`.

The confirmed internal endpoints (all POST with `content-type`, `x-xsrf-token`, and `x-kaggle-build-version` headers) are: `CompetitionService/ListCompetitions`, `SubmissionService/ListSubmissions`, `EpisodeService/ListEpisodes`, and `LeaderboardService/GetLeaderboard`; replays are fetched as `GET /competitions/episodes/{id}/replay.json`. The leaderboard call takes the numeric competition id (not the slug).

### How submission scores are determined

In simulation competitions a submission's visible score (a number usually in the hundreds or low thousands) is the agent's **skill rating**, not a metric like accuracy. Kaggle reports this rating inside the episode data — each episode carries an `agents` list of `{submissionId, reward, initialScore, updatedScore, teamId}`, and the rating after a match is `updatedScore`. It is *not* in the submission's `publicScoreFormatted` field, which is typically `0` or empty for these competitions.

The backend therefore derives a submission's score from the most recent episode's `updatedScore` for that submission's agent, and treats a literal `0`/empty formatted score as "unknown" rather than displaying a misleading `0`. Episode outcomes are computed from the same data: the submitting agent's terminal `reward` compared against the best reward among the other agents (greater is a win, less is a loss, tied at the top is a draw) — so outcome classification needs zero extra replay fetches.

### The rate-limit-safe design

This is the most important design decision in the project. The user interface never calls Kaggle directly on a page load or a navigation. Instead:

- All reads come from the MySQL cache.
- The cache is refreshed in exactly two ways: a **daily scheduler** (a pure-asyncio loop in the backend that runs at midnight UTC and refreshes competitions, submissions, episode lists, scores, and leaderboard snapshots), and a manual **Sync now** action you trigger yourself for a single competition.
- When cached data is older than the freshness window (24 hours by default), the app shows a "Last synced X ago" label but does not automatically re-fetch.
- Episode lookups that do hit Kaggle (the first time a submission is seen, or during a sync) are performed sequentially with a short delay and stop immediately on the first rate-limit response, leaving the rest to a later run.
- Resolving the top performers' replay IDs is bounded to the top 20 teams and paced, rather than firing one call per top-ten-percent team.

The net effect: normal browsing produces no Kaggle traffic at all, and the only live calls are paced and bounded.

## Architecture

The project was built in three phases, which still map cleanly onto the codebase:

| Layer | Responsibility |
|-------|----------------|
| `Backend/downloader.py` (Phase 1) | The original async Playwright module: the low-level functions that call Kaggle's internal API (list competitions / submissions / episodes, fetch replays in concurrent batches), classify episode outcomes from agent rewards, and package downloads with retry, resume, and outcome filtering. The web backend imports these functions directly rather than duplicating them. |
| `Backend/backend/` (Phase 2) | The FastAPI application: routers, services, background workers, MySQL models, JWT auth, a security layer (transport headers, strict CORS, slowapi rate limiting, an audit log, path-traversal guards), a per-user Playwright context pool, and the daily sync scheduler. |
| `Frontend/` (Phase 3) | The Vite + React + TypeScript single-page app: in-memory access token, WebSocket-driven live progress, light/dark themes, and the pages for competitions, submissions, downloads, leaderboard, and top replays. |
| `Database/` | The MySQL schema snapshot and migration references. |

The backend keeps routers thin: HTTP concerns live in `routers/`, Kaggle and persistence logic lives in `services/` and `tasks/`, and all database access goes through the SQLAlchemy ORM (no raw SQL).

## Tech stack

| Technology | Purpose |
|------------|---------|
| React 18 + TypeScript 5 (strict) | Frontend single-page application |
| Vite 5 | Frontend build tool and dev server |
| React Router 6 | Client-side routing |
| Axios | HTTP client (in-memory bearer token, refresh-on-401 interceptor) |
| Zustand | Frontend state management |
| Framer Motion | Animations and transitions |
| Tailwind CSS v4 | Styling |
| FastAPI | Backend REST + WebSocket API |
| Uvicorn | ASGI server |
| SQLAlchemy 2 (async) + aiomysql | ORM and async MySQL driver |
| Alembic | Database migrations |
| MySQL 8/9 | Database and local cache |
| Playwright | Authenticated headless browser used to reach Kaggle's internal API |
| python-jose | JWT access and rotating refresh tokens |
| slowapi | API rate limiting |
| structlog | Structured logging |

## Repository layout

```
.
├── Backend/
│   ├── downloader.py            # Phase 1: low-level Kaggle API client + replay downloader (async)
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
│       ├── alembic/             # database migrations 001..004
│       └── .env.example         # backend configuration template
├── Database/                    # schema snapshot + migration references
├── Frontend/
│   ├── src/                     # pages, components, api client, auth, store, types
│   ├── .env.example
│   └── package.json
├── docs/                        # project site (index.html) + documentation placeholders
├── .env.example                 # consolidated variable reference (backend + frontend)
├── CHANGELOG.md  CONTRIBUTING.md  LICENSE  README.md
└── .github/                     # issue + pull request templates
```

Secrets and per-user data (`auth.json`, `request.txt`, every `.env`, `sessions/`, `downloads/`, `logs/`, virtualenvs, `node_modules`) are excluded by `.gitignore` and must never be committed.

## Prerequisites

1. Node.js 18 or newer (required by Vite 5) and npm.
2. Python 3.12.
3. MySQL 8 or newer, running locally.
4. A Kaggle account that has entered at least one simulation competition. This app does not use a Kaggle API key. You log in once through a browser and the app saves the session to `auth.json`, so there is no `kaggle.json` to download.

## Getting started

1. Clone the repository.

   ```bash
   git clone https://github.com/[GITHUB_USERNAME]/kaggle-replays.git
   cd kaggle-replays
   ```

2. Create the MySQL database and a user (adjust the password).

   ```sql
   CREATE DATABASE kaggle_replays CHARACTER SET utf8mb4;
   CREATE USER 'kr_app'@'localhost' IDENTIFIED BY 'your_db_password';
   GRANT ALL PRIVILEGES ON kaggle_replays.* TO 'kr_app'@'localhost';
   FLUSH PRIVILEGES;
   ```

3. Set up the backend (from the repository root).

   ```bash
   cd Backend
   python3 -m venv .venv
   .venv/bin/python -m pip install -r backend/requirements.txt
   .venv/bin/python -m playwright install chromium
   ```

4. Configure backend environment variables.

   ```bash
   cp backend/.env.example backend/.env
   # Edit backend/.env: set DATABASE_URL (your password), JWT_SECRET and
   # JWT_REFRESH_SECRET (two different 64-hex strings), and DEV_LOGIN_ENABLED=true
   # for single-user local use. The repository root .env.example documents every variable.
   ```

5. Connect your Kaggle account and apply database migrations.

   ```bash
   .venv/bin/python login.py        # opens a browser; log in to Kaggle, then close it (writes auth.json)
   .venv/bin/python -m alembic -c backend/alembic.ini upgrade head
   ```

6. Start the backend.

   ```bash
   .venv/bin/python -m uvicorn backend.main:app --port 8000
   ```

   Health check: `curl http://127.0.0.1:8000/health` returns `{"status":"ok"}`. Interactive API docs are at http://127.0.0.1:8000/docs.

7. Set up and start the frontend (in a second terminal, from the repository root).

   ```bash
   cd Frontend
   npm install
   cp .env.example .env             # VITE_API_BASE_URL defaults to http://localhost:8000
   npm run dev
   ```

8. Open the app at http://localhost:5173 and click "Connect Kaggle Account".

Other useful commands: `npm run build` (type-check and production build), `npm run typecheck`, `npm run preview`.

## Environment variables

See `.env.example` in the repository root for the full list of variables (backend and frontend) with descriptions and example values. The backend reads `Backend/backend/.env`; the frontend reads `Frontend/.env`. Never commit your `.env` file; it is listed in `.gitignore`.

Key backend variables: `DATABASE_URL`, `JWT_SECRET` and `JWT_REFRESH_SECRET` (two different 64-hex secrets), `ALLOWED_ORIGINS` (CORS allow-list), `DEV_LOGIN_ENABLED`, `SESSIONS_BASE_DIR`, `DOWNLOADS_BASE_DIR`, and logging/concurrency tunables. The frontend uses a single variable, `VITE_API_BASE_URL`.

## Using the application

1. **Home** lists your competitions. Open one to see its submissions.
2. **Submissions** shows each submission's score and episode count. Press **Sync now** to force a fresh pull from Kaggle; otherwise data is served from the local cache, and a "Last synced" label shows how fresh it is.
3. **Leaderboard** (from the sidebar or a competition) shows the current public standings and the top-ten-percent cutoff, with a competition selector and search.
4. **Top 10% Replays** shows dated leaderboard snapshots and the replay episode IDs of the top performers. Press **Sync now** to capture today's standings and the top performers' replays.
5. From a submission you can bulk-download replays (JSON or ZIP), optionally filtered by outcome, and watch live progress.

## Security model and deployment warning

The backend ships with a deliberate security layer: JWT access tokens (15 minutes) with rotating refresh tokens delivered as httponly, secure, SameSite=strict cookies; a per-user concurrent-session cap; transport-security response headers on every response; a strict CORS allow-list; slowapi rate limits with blocked requests written to an audit log; Pydantic request bodies that reject unknown fields; ORM-only database access; and path-traversal-guarded file operations. The access token is held only in browser memory, never in local storage, so a new tab must re-authenticate (an intentional trade-off).

Despite all of this, please read this carefully:

> Do not deploy this as a public, multi-user website using your own Kaggle session. The application authenticates to Kaggle as *you* via `auth.json`. Hosting it publicly would place your live Kaggle credentials on a server and expose your account to anyone who can reach it, and automated traffic against Kaggle's internal API may violate Kaggle's Terms of Service. This project is intended to run locally, for your own account. If you want a public presence, publish a static landing/documentation page (see `docs/index.html`) and keep the live application local. `DEV_LOGIN_ENABLED` must be left false/unset in any non-local context.

## API reference

| Method | Path | Notes |
|--------|------|-------|
| POST | `/auth/kaggle-login`, `/auth/refresh`, `/auth/logout` | JWT; refresh rotates; rate limited |
| GET / PATCH | `/auth/me` | current user (the PATCH exists but the profile UI is read-only) |
| GET | `/competitions`, `/competitions/{kaggleId}/submissions` | user-scoped, served from cache |
| POST | `/competitions/{kaggleId}/sync` | manual "Sync now": background refresh of submissions, episodes, scores, leaderboard |
| GET | `/submissions/{id}/episodes?filter=` | episode IDs + outcomes, served from cache |
| POST | `/downloads/start`, `/downloads/bulk` | background download jobs |
| GET / DELETE | `/downloads`, `/downloads/{uuid}/status`, `/downloads/{uuid}/file`, `/downloads/{uuid}` | history / progress / ZIP stream / cancel |
| WS | `/ws/downloads/{uuid}?token=` | live progress |
| GET | `/leaderboard/{kaggleId}/current`, `/leaderboard/{kaggleId}/history`, `/leaderboard/{kaggleId}/date/{date}/replays` | current standings / daily snapshots |
| POST | `/leaderboard/{kaggleId}/sync` | daily sync or historical backfill |

Note: leaderboard and submission routes both accept the Kaggle numeric competition id (the value used throughout the frontend) and resolve the internal record from it.

## Database migrations

Managed by Alembic (`Backend/backend/alembic/`). Apply with `.venv/bin/python -m alembic -c backend/alembic.ini upgrade head`.

| Revision | Adds |
|----------|------|
| `001_initial` | users, sessions, playwright sessions, competitions, submissions, download jobs, audit log, rate-limit log |
| `002_leaderboard_tables` | leaderboard snapshots, entries, and top-performer episodes |
| `003_profile_and_competition_fields` | user profile fields (thumbnail, profile URL, tier) and competition status fields (deadline, category, enabled date, is_simulation) |
| `004_episode_cache` | `submissions.episodes_json` and `submissions.episodes_synced_at` so episode IDs are served from the DB cache |

All migrations are additive and nullable; none require a data migration.

## Development journey and issues faced

This section is the practical history of the project: the problems that came up and how each was resolved. It is useful both as a record and as a guide to the non-obvious parts of the code.

### Phase 1 — the downloader (CLI)

The first deliverable was `downloader.py`: an async Playwright script that authenticates with a saved Kaggle session and drives the internal API to list competitions, submissions, and episodes, then download replays in concurrent batches with retry, resume, outcome filtering, and ZIP packaging. The key discovery here was the **outcome schema**: each episode dict carries an `agents` list with `reward`, `initialScore`, and `updatedScore`, so a match's winner (and each agent's skill rating) can be read directly from the episode without fetching the replay body. This is why outcome classification later costs zero extra requests.

### Phase 2 — the backend (FastAPI + MySQL)

The downloader's functions were wrapped in a FastAPI service with MySQL persistence, JWT auth, a per-user Playwright context pool, WebSocket download progress, and a full security layer (headers, CORS allow-list, rate limiting, audit log, path-traversal guards). The leaderboard endpoint (`GetLeaderboard`) was discovered by live request interception; its body takes the numeric competition id and returns a `publicLeaderboard` list joined to a `teams` list by team id.

### Phase 3 — the frontend (React + TypeScript)

A Vite/React/TypeScript SPA with an in-memory-only access token, a refresh-on-401 axios interceptor, and a WebSocket-driven live download view. The UI went through three visual iterations: an initial Bootstrap build, a migration to a Tailwind-based design, and a final redesign to a warm ivory-and-clay theme with full light/dark support.

### Issues faced and how they were solved

**Rate limiting (the recurring theme).** Kaggle returns `429 RESOURCE_EXHAUSTED` for bursts against its internal API. Several iterations were needed:
- Episode counts were first fetched with a parallel `Promise.all`, which immediately tripped the limit. This was rewritten to sequential calls with a delay and a stop-on-429 guard.
- A short-TTL in-memory cache was added so repeat browsing did not re-hit Kaggle.
- The final design moved all reads to the MySQL cache and restricted live calls to a daily scheduler and an explicit "Sync now" — the rate-limit-safe model described above.
- Resolving the top performers' replay IDs originally fired one `ListEpisodes` call per top-ten-percent team (hundreds of calls), which storm-tripped the limit and stored nothing. It was bounded to the top 20 and paced, with stop-on-429.

**Submission scores showing 0.** For simulation competitions, `publicScoreFormatted` is `0`/empty; the real score is the agent skill rating (`updatedScore`) carried in the episode data. The fix sources the score from the latest episode's rating and treats `0`/empty as "unknown" (rendered as a dash) so a misleading `0` is never shown.

**Leaderboard empty and Top 10% Replays history errors.** These shared one root cause. The frontend routes carry the Kaggle numeric competition id, and the submissions endpoint resolved by that id correctly, but the leaderboard routes resolved by the internal primary key — so they returned 404, which surfaced as an empty leaderboard and a "Could not load top-replay history" error (doubled by React StrictMode in development). The fix makes the leaderboard routes resolve by the Kaggle id and use the internal id only for snapshot relationships.

**Login showing two "too many requests" popups.** React StrictMode double-invokes effects in development, so the auth bootstrap fired two `/auth/refresh` calls; when those hit the auth rate limit, the client showed two 429 toasts. The fix suppresses 429 toasts for auth endpoints (a throttled background refresh should fail silently to logged-out) and coalesces the bootstrap into a single shared refresh.

**"Could not start the Kaggle login flow."** This one is operational, not a code bug: it appears when the backend process is not running (the frontend's login request is refused). Start the backend and it resolves.

**Top 10% Replays showing only names.** The "Backfill" button reconstructed a degenerate single-team list from the user's own submissions, with no real team names and no episode IDs — which made the page redundant with the leaderboard. It was replaced with a real leaderboard capture that stores actual team names and, via the bounded resolver above, the top performers' replay episode IDs.

**Episode counts showing 0 when rate-limited.** A throttled `ListEpisodes` response was once recorded as "0 episodes." The column was made nullable so an unknown count is distinct from a confirmed `0`, rendered as a dash, and filled in later by the background resolver.

**Password hashing crash on login.** A version mismatch between `passlib` and `bcrypt` caused every login to raise. The fix calls `bcrypt` directly.

**Profile editing.** The profile was made fully read-only because Kaggle is the source of truth; the panel links out to Kaggle for edits. The richer profile fields (competition points, medals, bio, location, organization, joined date) are not present in the login token and were intentionally not added, since fetching them would require a separate Kaggle call and a schema change.

**Frontend polish.** Along the way: fixed a grid-misalignment bug where data-table headers and rows used different column grids; removed an error-banner loop where a polling effect re-fired a failing request and stacked toasts; replaced all emoji with an inline SVG icon set; and added a real dark theme.

### Open source and hosting

Preparing the repository for public release involved a secret audit (no hardcoded secrets in tracked files; `auth.json`, `request.txt`, and `.env` are gitignored), a comprehensive `.gitignore`, this README, a root `.env.example`, an MIT `LICENSE`, `CONTRIBUTING.md`, `CHANGELOG.md`, GitHub issue and pull request templates, and a `docs/` folder. Because the live app cannot safely be public (it uses your personal Kaggle session), the intended "website" is the static page in `docs/` served via GitHub Pages, while the application itself runs locally.

## Troubleshooting

- **"Could not start the Kaggle login flow"** in the UI: the backend is not running, or the frontend is pointed at the wrong `VITE_API_BASE_URL`. Start the backend and confirm `curl http://127.0.0.1:8000/health`.
- **Empty data or "Kaggle session expired"**: your `auth.json` lapsed. Re-run `python login.py`.
- **"Kaggle is rate-limiting requests (429)"**: Kaggle throttled a burst. Wait a few minutes; the app surfaces this clearly and will not record a throttled response as zero episodes. Prefer "Sync now" over repeated manual refreshes.
- **Scores or episode counts show a dash**: the value has not been resolved yet. It fills in after the background resolve completes, or after a "Sync now".

## Limitations and responsible use

- This tool uses Kaggle's internal API through your own logged-in session. It is provided for personal, educational use with your own account and data. Respect Kaggle's Terms of Service, and do not use it to place undue load on Kaggle's services or to access data that is not yours.
- It targets simulation/episode competitions; predictive (metric-scored) competitions are only partially relevant, since their scoring differs.
- It is single-user and local by design (see the security warning).

## Contributing

Contributions are welcome. See `CONTRIBUTING.md` for how to report bugs, suggest features, and open a pull request.

## License

This project is licensed under the MIT License. See the LICENSE file for details.

## Acknowledgements

Built on FastAPI, SQLAlchemy, Playwright, React, and Vite. "Kaggle" is a trademark of its respective owner; this project is independent and not affiliated with or endorsed by Kaggle or Google.

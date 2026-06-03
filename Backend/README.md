# Backend — Kaggle Replay Analytics Platform

Phases 1 + 2 of the platform:

- **Phase 1 — `downloader.py`**: async Playwright CLI that downloads Kaggle
  competition episode replays (concurrent batches, outcome filtering, ZIP,
  resume, bulk mode). See `improvements.md` for the roadmap.
- **Phase 2 — `backend/`**: FastAPI server wrapping the downloader in a REST +
  WebSocket API with MySQL, JWT auth, a full security layer, and a Top-10%
  Daily Leaderboard feature.

## Layout

```
Backend/
├── downloader.py            # Phase 1 CLI (imported by the backend worker)
├── improvements.md          # roadmap
├── login.py, competitions.py, submissions.py, inspect_*.py, test*.py
│                            # original Phase 1 helper scripts (login.py creates auth.json)
├── auth.json                # live Playwright session (gitignored — do not commit)
├── request.txt              # captured API headers reference (gitignored)
├── .venv/                   # this folder's virtualenv (gitignored)
└── backend/                 # the FastAPI application package
    ├── main.py              # app factory + lifespan (starts leaderboard scheduler)
    ├── config.py database.py models.py schemas.py security.py
    ├── middleware.py dependencies.py audit.py logging_config.py
    ├── session_manager.py   # per-user Playwright context pool (LRU)
    ├── kaggle_service.py     # bridge to ../downloader.py + leaderboard fetch
    ├── routers/             # auth, competitions, submissions, downloads, ws, leaderboard
    ├── services/            # auth, download, kaggle_data (keeps routers thin)
    ├── tasks/               # download_worker, leaderboard_worker (+ scheduler)
    ├── utils/               # file_utils (safe paths/zip/stream), sanitize
    ├── alembic/             # migrations 001_initial, 002_leaderboard_tables
    ├── .env / .env.example  # config (real .env gitignored)
    └── requirements.txt
```

## Run

```bash
# 0. MySQL must be running and backend/.env configured (see ../Database/README.md)

# 1. Create your Kaggle session (writes auth.json via an interactive login).
#    Required before the web login or the CLI can fetch any data. Re-run this
#    whenever the session expires (symptom: "Kaggle session expired" / empty data).
.venv/bin/python login.py        # opens a browser → log into Kaggle → close it

# 2. Apply migrations
.venv/bin/python -m alembic -c backend/alembic.ini upgrade head

# 3. Start the API (from THIS directory so `backend.main` resolves)
.venv/bin/python -m uvicorn backend.main:app --reload --port 8000
```

Health check: `curl http://127.0.0.1:8000/health` → `{"status":"ok"}`.
Interactive docs: http://127.0.0.1:8000/docs

### Local web login (DEV_LOGIN_ENABLED)

For single-user local use, set `DEV_LOGIN_ENABLED=true` in `backend/.env`. The
frontend's **Connect Kaggle Account** button then logs in using this folder's
`auth.json` (no manual token juggling). If `auth.json` is missing, the button
shows a friendly "No Kaggle session found — run `python login.py`" message
instead of an error. Leave `DEV_LOGIN_ENABLED` unset/false for any real
deployment.

### Troubleshooting

- **"Kaggle is rate-limiting requests (429)"** — Kaggle throttles bursts of
  `ListEpisodes`/leaderboard calls. Wait a few minutes and retry; the app now
  surfaces this clearly and will not record a throttled response as "0 episodes".
- **Empty competitions/submissions or "session expired"** — your `auth.json`
  session lapsed; re-run `python login.py`.

## Phase 1 CLI

```bash
.venv/bin/python downloader.py --help
.venv/bin/python downloader.py --headless --inspect      # discover episode/replay structure
.venv/bin/python downloader.py --headless --filter win --format zip
```

> `auth.json` is created by `python login.py` (interactive Kaggle login). It and
> `request.txt` hold live session secrets and are gitignored.

## Key API endpoints

| Method | Path | Notes |
|--------|------|-------|
| POST | `/auth/kaggle-login`, `/auth/refresh`, `/auth/logout` | JWT; 5/15min rate limit |
| GET | `/auth/me` | current user |
| GET | `/competitions`, `/competitions/{id}/submissions` | user-scoped, cached |
| GET | `/submissions/{id}/episodes?filter=` | outcomes computed (zero extra fetch) |
| POST | `/downloads/start`, `/downloads/bulk` | background job; 10/hr, 3/hr |
| GET | `/downloads`, `/downloads/{uuid}/status`, `/downloads/{uuid}/file` | history / progress / ZIP stream |
| DELETE | `/downloads/{uuid}` | cancel + delete output |
| WS | `/ws/downloads/{uuid}?token=` | live progress |
| GET | `/leaderboard/{id}/history`, `/leaderboard/{id}/date/{date}/replays` | top-10% daily |
| POST | `/leaderboard/{id}/sync` | daily sync or backfill; 2/hr |

## Security highlights

JWT access (15 min) + rotating refresh (httponly cookie); per-user session cap;
7 transport-security headers on every response; strict CORS allow-list; slowapi
rate limits with `audit_log` on blocks; Pydantic `extra=forbid` request bodies;
SQLAlchemy ORM only (no raw SQL); path-traversal-guarded file ops; per-user
`auth.json` at `0600`.

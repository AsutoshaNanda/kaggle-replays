# Future Roadmap — Kaggle Replay Downloader

This document tracks the planned evolution of `downloader.py` from a
single-context CLI into a full replay-analytics platform. Items are roughly
ordered from "natural next step" to "longer-term".

## 1. Async Multi-Context Architecture
The current design downloads concurrently *within* one browser context using
`Promise.all`, but every submission is still processed sequentially. A pool of
several Playwright `BrowserContext` objects (capped by the existing
`MAX_WORKERS` constant) would let independent submissions download in true
parallel. Each context would carry its own authenticated session derived from
`auth.json`, and a worker queue would hand submissions out to whichever context
is free. This would cut wall-clock time for bulk mode roughly linearly with the
number of contexts, bounded by Kaggle's rate limits and local CPU/RAM. Care is
needed to back off globally when any context starts seeing HTTP 429s.

## 2. FastAPI Web Server Integration
Expose every capability of `downloader.py` (list competitions, list
submissions, list episodes, start a download, stream progress) as REST
endpoints behind a FastAPI application. JWT-based auth would gate the endpoints
so the planned React frontend can trigger downloads on a user's behalf without
ever handling Kaggle cookies directly. The long-running download work would run
as background tasks, with a job table tracking status and a WebSocket pushing
live progress. This is the bridge from "local script" to "multi-user web app"
and is the immediate next phase of the project.

## 3. SQLite/MySQL Episode Database
Replace the "does the JSON file exist?" resume check with a proper database
that records every downloaded episode: its ID, competition, submission, score,
computed outcome, file path, byte size, and download timestamp. SQLite is ideal
for the local CLI; MySQL for the multi-user server. A real index on
`(submission_id, episode_id)` makes deduplication instant even across hundreds
of thousands of rows, and the same table becomes the foundation for analytics
queries ("win rate by opponent", "score over time"). Migrations would keep the
schema versioned as new fields are discovered via `--inspect`.

## 4. Resume-from-Checkpoint
Bulk runs over thousands of episodes should survive interruption (network drop,
Ctrl-C, expired session). Writing a small JSON manifest as the download
progresses — recording which episode IDs are done, pending, or permanently
failed — lets a re-run pick up exactly where it left off instead of relying
solely on file existence. The manifest would also capture the chosen filter and
format so a resumed run stays consistent with the original. Combined with the
database in item 3, this makes very large bulk jobs reliable and observable.

## 5. Replay Parser & Analytics Engine
Each replay JSON contains a rich per-step structure (board state, actions,
rewards, and statuses for every agent on every turn). A dedicated parser would
turn this into tidy tabular data — one row per (episode, step, agent) — enabling
statistical analysis of strategy and performance. From there we can compute
things like average reward trajectories, action-frequency distributions, and
turn-by-turn win-probability estimates. This engine is what elevates the tool
from "replay downloader" to "replay *analytics* platform".

## 6. Docker Containerization
Ship a `Dockerfile` and `docker-compose.yml` that bake in Python, the exact
pinned dependencies, and a pre-installed Chromium with all of Playwright's
system libraries. This removes the "works on my machine" friction of
Playwright's heavy native dependencies and gives every contributor an identical
environment. Compose would wire the downloader/API container to a database
container for the full stack. A volume mount would keep `auth.json` and the
`downloads/` output on the host so sessions and data persist across container
rebuilds.

## 7. Leaderboard Meta Analysis
With outcomes and replay details captured for thousands of episodes across many
submissions, we can analyse the competitive meta-game rather than a single
agent. Aggregations would surface which opponents are most common, which
strategies beat which, and how the meta shifts over time as the leaderboard
evolves. This turns the raw replay archive into actionable competitive
intelligence — e.g. "agents using strategy X have a 60% win rate against the
current top 10". It depends on a reliable `determine_outcome()` and the
analytics engine from item 5.

## 8. Scheduled Auto-Sync
A background scheduler (cron-style, or an async loop) would periodically check
each tracked submission for new episodes and download only the deltas. This
keeps the local archive and database continuously up to date without manual
re-runs, which matters because Kaggle simulation competitions generate fresh
episodes continuously. Sensible defaults — a daily sync, with per-competition
overrides — plus the resume/checkpoint machinery from item 4 would make it
robust. Notifications (email or webhook) on new wins or losses would close the
loop into a hands-off monitoring system.

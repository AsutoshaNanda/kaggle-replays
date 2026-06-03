# Kaggle Replays

Browse, view, and bulk-download the episode replays from your Kaggle simulation competitions, all from one local web app.

![Build](https://img.shields.io/github/actions/workflow/status/[GITHUB_USERNAME]/kaggle-replays/ci.yml?label=build) ![License](https://img.shields.io/badge/license-MIT-green) ![Version](https://img.shields.io/badge/version-0.1.0-blue)

## Demo

[ADD SCREENSHOT OR GIF HERE]

## What It Does

Kaggle simulation competitions (the "Game Arena" style competitions where you submit an agent that plays matches) generate large numbers of episode replays, but the Kaggle website only lets you reach them one at a time. Kaggle Replays is a local web app that gives you a single place to browse the competitions you have entered, inspect each submission and its episodes, filter those episodes by outcome (win, loss, or draw), and download their replays in bulk for offline analysis. It also shows the live leaderboard and the daily top performers, so you can study how the best agents are playing. It is built for Kaggle competitors who want to analyze replays at scale without manually clicking through the site.

## Features

- Browse the competitions you have entered, with active and completed status.
- View submissions for a competition, including each submission's real skill-rating score and episode count.
- List a submission's episodes with an automatically computed outcome (win, loss, or draw).
- Bulk-download replays as JSON or ZIP, optionally filtered by outcome, with live progress over a WebSocket.
- View the current public leaderboard with a top-ten-percent cutoff, search, and a competition selector.
- See "Top 10% Replays": daily leaderboard snapshots and the replay episode IDs of the top performers.
- A read-only profile panel sourced from your Kaggle session.
- A rate-limit-safe data layer: the interface always reads from a local cache and only refreshes from Kaggle on a schedule or an explicit sync.
- [PASTE: add any additional features]

## Tech Stack

| Technology | Purpose |
|------------|---------|
| React 18 + TypeScript | Frontend single-page application |
| Vite 5 | Frontend build tool and dev server |
| React Router 6 | Client-side routing |
| Axios | HTTP client for the backend API |
| Zustand | Frontend state management |
| Tailwind CSS v4 | Styling |
| FastAPI | Backend REST + WebSocket API |
| Uvicorn | ASGI server that runs the backend |
| SQLAlchemy 2 (async) + aiomysql | ORM and async MySQL driver |
| Alembic | Database migrations |
| MySQL | Database / local cache |
| Playwright | Authenticated headless browser used to reach Kaggle's internal API |
| python-jose | JWT access and refresh tokens |
| slowapi | API rate limiting |
| structlog | Structured logging |

## Prerequisites

1. Node.js 18 or newer (required by Vite 5) and npm.
2. Python 3.12.
3. MySQL 8 or newer, running locally.
4. A Kaggle account that has entered at least one simulation competition. Note: this app does not use a Kaggle API key. You log in once through a browser (a script saves the session to `auth.json`), so there is no `kaggle.json` to download.

## Getting Started

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

7. Set up and start the frontend (in a second terminal, from the repository root).

   ```bash
   cd Frontend
   npm install
   cp .env.example .env             # VITE_API_BASE_URL defaults to http://localhost:8000
   npm run dev
   ```

8. Open the app in your browser at http://localhost:5173 and click "Connect Kaggle Account".

## Environment Variables

See `.env.example` in the repository root for the full list of variables (backend and frontend) with descriptions and example values. Never commit your `.env` file; it is listed in `.gitignore`.

## Contributing

Contributions are welcome. See `CONTRIBUTING.md` for how to report bugs, suggest features, and open a pull request.

## License

This project is licensed under the MIT License. See the LICENSE file for details.

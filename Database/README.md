# Database — Kaggle Replay Analytics Platform

MySQL schema for the platform. The **authoritative** schema is defined by the
SQLAlchemy ORM models in `../Backend/backend/models.py` and applied via Alembic
migrations in `../Backend/backend/alembic/versions/`. The files here are a
convenience snapshot + reference.

## Contents

| File | Purpose |
|------|---------|
| `schema.sql` | Full `mysqldump --no-data` of the live schema (all 11 app tables + `alembic_version`). Reference only — do **not** hand-edit and re-import in place of migrations. |
| `migrations_reference/001_initial.py` | Copy of the core-tables migration (7 tables). The runnable original lives under `../Backend/backend/alembic/versions/`. |
| `migrations_reference/002_leaderboard_tables.py` | Copy of the leaderboard migration (3 tables). |

## Tables (11)

**Core (migration 001):**
`users`, `user_sessions`, `playwright_sessions`, `competitions`, `submissions`,
`download_jobs`, `audit_log`, `rate_limit_log`

**Leaderboard feature (migration 002):**
`leaderboard_snapshots`, `leaderboard_entries`, `top_performer_episodes`

## First-time setup (Homebrew MySQL)

```bash
# 1. Install + start MySQL (once)
brew install mysql
brew services start mysql

# 2. Create the database and an application user
mysql -u root <<'SQL'
CREATE DATABASE IF NOT EXISTS kaggle_replays
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'kr_app'@'localhost' IDENTIFIED BY 'CHANGE_ME';
-- Runtime needs SELECT/INSERT/UPDATE/DELETE. Migrations additionally need DDL
-- (CREATE/ALTER/DROP/INDEX); grant DDL for setup, then it is unused at runtime.
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, DROP, INDEX, REFERENCES
  ON kaggle_replays.* TO 'kr_app'@'localhost';
FLUSH PRIVILEGES;
SQL
```

## Apply / create the schema (preferred: Alembic)

```bash
cd ../Backend            # so backend.config can load backend/.env
.venv/bin/python -m alembic -c backend/alembic.ini upgrade head
```

Set the connection string in `../Backend/backend/.env`:

```
DATABASE_URL=mysql+aiomysql://kr_app:CHANGE_ME@127.0.0.1:3306/kaggle_replays
```

## Recreate from the SQL snapshot (alternative, e.g. fresh clone)

```bash
mysql -u root kaggle_replays < schema.sql
```

> The snapshot has no `INSERT`s — it is structure only and contains no
> credentials or user data.

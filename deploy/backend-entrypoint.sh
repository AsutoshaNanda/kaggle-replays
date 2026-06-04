#!/usr/bin/env sh
set -e

# Runtime data dirs live on a persistent volume (see docker-compose.yml).
mkdir -p /data/sessions /data/downloads /data/logs

# Apply migrations, retrying while MySQL finishes warming up.
n=0
until python -m alembic -c backend/alembic.ini upgrade head; do
  n=$((n + 1))
  if [ "$n" -ge 20 ]; then
    echo "Database not reachable after many attempts; giving up." >&2
    exit 1
  fi
  echo "Migration attempt failed (database warming up?); retrying in 3s..."
  sleep 3
done

exec python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000

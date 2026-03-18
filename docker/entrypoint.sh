#!/bin/sh
set -e

echo "Waiting for database to be ready..."
python - <<'PY'
import os
import time

from sqlalchemy import create_engine, text

url = os.environ["SKAVA_DATABASE_URL"]
engine = create_engine(url, pool_pre_ping=True)

last_error = None
for attempt in range(1, 31):
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print(f"Database ready (attempt {attempt}).")
        break
    except Exception as exc:  # pragma: no cover
        last_error = exc
        print(f"Database not ready yet (attempt {attempt}/30): {exc}")
        time.sleep(2)
else:
    raise SystemExit(f"Database did not become ready in time: {last_error}")
PY

echo "Running migrations..."
alembic upgrade head

echo "Seeding data..."
python -m app.seed

echo "Starting API..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000

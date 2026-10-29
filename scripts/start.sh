#!/bin/sh
set -e

echo "Running database migrations..."
alembic upgrade head

echo "Seeding database (safe to re-run)..."
python -m scripts.seed

PORT="${PORT:-8000}"
echo "Starting API on port ${PORT}..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT}"

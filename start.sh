#!/bin/bash
set -e

echo "Starting Circles application..."

# Wait for database to be ready
echo "Waiting for database connection..."
sleep 5

# Run database migrations
echo "Running database migrations..."
uv run alembic upgrade head || {
    echo "Migration failed, but continuing with startup..."
    echo "Database might already be up to date"
}

# Start the application
echo "Starting FastAPI application..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000

#!/bin/bash
set -e

# Sync code data files (taxonomy, rating tables) from staging to volume
# This ensures the volume always has the latest versions after each deploy
if [ -d /app/data-staging ]; then
    echo "Syncing data files to volume..."
    cp -f /app/data-staging/* /app/data/ 2>/dev/null || true
fi

# Initialize database if it doesn't exist
if [ ! -f "${DATABASE_PATH:-/app/data/financial_analysis.db}" ]; then
    echo "Initializing database..."
    cd /app && python -c "from database.db import init_db; init_db()"
fi

# Start uvicorn
cd /app/backend
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2

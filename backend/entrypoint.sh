#!/bin/bash
set -e

# Initialize database if it doesn't exist
if [ ! -f "${DATABASE_PATH:-/app/data/financial_analysis.db}" ]; then
    echo "Initializing database..."
    cd /app && python -c "from database.db import init_db; init_db()"
fi

# Start uvicorn
cd /app/backend
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2

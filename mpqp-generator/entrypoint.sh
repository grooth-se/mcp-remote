#!/bin/sh
set -e

echo "=== MPQP Generator starting ==="

DATABASE_URL="${DATABASE_URL:-}"

# Wait for PostgreSQL if using postgres
if echo "$DATABASE_URL" | grep -q "^postgresql"; then
    echo "Waiting for PostgreSQL..."
    for i in $(seq 1 30); do
        if python -c "
import psycopg2, os
conn = psycopg2.connect(os.environ['DATABASE_URL'])
conn.close()
" 2>/dev/null; then
            echo "Database ready."
            break
        fi
        echo "  Attempt $i/30..."
        sleep 2
    done
else
    echo "Using SQLite database."
fi

# Initialize database
echo "Initializing database..."
python -c "
from app import create_app, db
app = create_app()
with app.app_context():
    db.create_all()
    print('Database tables created.')
"

# Start gunicorn
echo "Starting gunicorn..."
exec gunicorn \
    --bind 0.0.0.0:5003 \
    --workers ${GUNICORN_WORKERS:-2} \
    --timeout ${GUNICORN_TIMEOUT:-300} \
    --access-logfile - \
    --error-logfile - \
    "app:create_app()"

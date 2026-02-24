#!/bin/bash
set -e

echo "=== HeatSim Starting ==="

# Initialize database tables before gunicorn starts
echo "Initializing database..."
python -c "
from app import create_app
from app.extensions import db

app = create_app('production')
with app.app_context():
    db.create_all()
    print('All database tables created.')

    # Check materials bind tables
    import sqlalchemy as sa
    mat_engine = db.engines.get('materials')
    if mat_engine:
        inspector = sa.inspect(mat_engine)
        tables = inspector.get_table_names()
        print(f'Materials DB: {len(tables)} tables ready.')
"

echo "=== Starting Gunicorn ==="
exec gunicorn \
    --bind 0.0.0.0:5000 \
    --timeout 300 \
    --workers 1 \
    --threads 4 \
    "run:app"

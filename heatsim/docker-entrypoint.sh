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

    # Auto-migrate: add missing columns to existing tables
    import sqlalchemy as sa
    inspector = sa.inspect(db.engine)
    with db.engine.connect() as conn:
        if 'users' in inspector.get_table_names():
            cols = [c['name'] for c in inspector.get_columns('users')]
            if 'display_name' not in cols:
                conn.execute(sa.text('ALTER TABLE users ADD COLUMN display_name VARCHAR(120)'))
                print('  Added display_name column to users')
            if 'is_active_user' not in cols:
                conn.execute(sa.text('ALTER TABLE users ADD COLUMN is_active_user BOOLEAN DEFAULT 1'))
                print('  Added is_active_user column to users')
            conn.commit()

    # Check materials bind tables
    mat_engine = db.engines.get('materials')
    if mat_engine:
        mat_inspector = sa.inspect(mat_engine)
        tables = mat_inspector.get_table_names()
        print(f'Materials DB: {len(tables)} tables ready.')
"

# Start virtual framebuffer for PyVista off-screen rendering
echo "Starting Xvfb..."
Xvfb :99 -screen 0 1024x768x24 &

echo "=== Starting Gunicorn ==="
exec gunicorn \
    --bind 0.0.0.0:5000 \
    --timeout 300 \
    --workers 1 \
    --threads 4 \
    "app:create_app('production')"

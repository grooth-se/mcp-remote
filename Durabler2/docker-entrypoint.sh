#!/bin/bash
set -e

echo "=== Durabler2 Starting ==="

# Wait for database to be ready
echo "Waiting for database..."
python -c "
import time, os
from sqlalchemy import create_engine, text

url = os.environ.get('DATABASE_URL', '')
if not url:
    print('No DATABASE_URL set, skipping DB wait')
    exit(0)

for i in range(30):
    try:
        engine = create_engine(url)
        with engine.connect() as conn:
            conn.execute(text('SELECT 1'))
        print('Database is ready!')
        break
    except Exception as e:
        print(f'Waiting for database... ({i+1}/30)')
        time.sleep(2)
else:
    print('ERROR: Database not available after 60 seconds')
    exit(1)
"

# Run database migrations or create tables
echo "Initializing database..."
python -c "
import os
os.environ.setdefault('FLASK_CONFIG', 'production')

from app import create_app, db
from app.models import User
from sqlalchemy import inspect, text

app = create_app(os.environ.get('FLASK_CONFIG', 'production'))

with app.app_context():
    # Auto-migrate: add missing columns to existing tables
    # db.create_all() only creates NEW tables, not new columns
    insp = inspect(db.engine)
    existing_tables = insp.get_table_names()

    for table in db.metadata.sorted_tables:
        if table.name in existing_tables:
            existing_cols = {c['name'] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name not in existing_cols:
                    col_type = col.type.compile(db.engine.dialect)
                    default = ''
                    if col.default is not None:
                        val = col.default.arg
                        if isinstance(val, bool):
                            default = f' DEFAULT {1 if val else 0}'
                        elif isinstance(val, (int, float)):
                            default = f' DEFAULT {val}'
                        elif isinstance(val, str):
                            default = f\" DEFAULT '{val}'\"
                    elif col.nullable:
                        default = ' DEFAULT NULL'
                    sql = f'ALTER TABLE {table.name} ADD COLUMN {col.name} {col_type}{default}'
                    print(f'  Adding column: {table.name}.{col.name} ({col_type})')
                    db.session.execute(text(sql))
            db.session.commit()

    # Create any entirely new tables
    db.create_all()
    print('Database tables ready.')

    # Create admin user if it doesn't exist
    admin_username = os.environ.get('ADMIN_USERNAME', 'admin')
    admin_password = os.environ.get('ADMIN_PASSWORD', 'admin')

    existing = User.query.filter_by(username=admin_username).first()
    if not existing:
        admin = User(
            username=admin_username,
            role='admin',
            full_name='Administrator',
            user_id='DUR-ADM-001'
        )
        admin.set_password(admin_password)
        db.session.add(admin)
        db.session.commit()
        print(f'Admin user \"{admin_username}\" created.')
    else:
        # Ensure admin user always has admin role
        if existing.role != 'admin':
            existing.role = 'admin'
            db.session.commit()
            print(f'Admin user \"{admin_username}\" role corrected to admin.')
        else:
            print(f'Admin user \"{admin_username}\" already exists.')
"

echo "=== Starting Gunicorn ==="
exec gunicorn \
    --bind 0.0.0.0:5000 \
    --workers 4 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile - \
    --capture-output \
    --log-level info \
    "run:app"

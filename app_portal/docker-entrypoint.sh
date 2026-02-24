#!/bin/bash
set -e

echo "=== Subseatec App Portal Starting ==="

# Initialize database and seed default apps
echo "Initializing database..."
python -c "
import os
os.environ.setdefault('FLASK_APP', 'app:create_app')

from app import create_app
from app.extensions import db
from app.models.user import User
from app.models.application import Application

app = create_app()
with app.app_context():
    db.create_all()
    print('Database tables created.')

    # Ensure new columns exist (for upgrades without migration)
    import sqlalchemy as sa
    inspector = sa.inspect(db.engine)
    with db.engine.connect() as conn:
        app_cols = [c['name'] for c in inspector.get_columns('applications')]
        if 'available_roles' not in app_cols:
            conn.execute(sa.text('ALTER TABLE applications ADD COLUMN available_roles TEXT'))
            print('  Added available_roles column')
        if 'default_role' not in app_cols:
            conn.execute(sa.text('ALTER TABLE applications ADD COLUMN default_role VARCHAR(50)'))
            print('  Added default_role column')
        perm_cols = [c['name'] for c in inspector.get_columns('user_permissions')]
        if 'role' not in perm_cols:
            conn.execute(sa.text('ALTER TABLE user_permissions ADD COLUMN role VARCHAR(50)'))
            print('  Added role column to user_permission')
        conn.commit()

    # Seed default applications (insert new, update existing)
    from scripts.init_db import DEFAULT_APPS
    for app_data in DEFAULT_APPS:
        existing = Application.query.filter_by(app_code=app_data['app_code']).first()
        if not existing:
            application = Application(**app_data)
            db.session.add(application)
            print(f'  Added: {app_data[\"app_name\"]}')
        else:
            for key, value in app_data.items():
                if key == 'app_code':
                    continue
                if getattr(existing, key, None) != value:
                    setattr(existing, key, value)
                    print(f'  Updated {app_data[\"app_name\"]}: {key}')
    db.session.commit()

    # Create admin user if none exists
    admin = User.query.filter_by(is_admin=True).first()
    if not admin:
        admin_user = os.environ.get('ADMIN_USERNAME', 'admin')
        admin_pass = os.environ.get('ADMIN_PASSWORD', '')
        if admin_pass:
            user = User(
                username=admin_user,
                display_name='Administrator',
                is_admin=True,
            )
            user.set_password(admin_pass)
            db.session.add(user)
            db.session.commit()
            print(f'Admin user \"{admin_user}\" created.')
        else:
            print('WARNING: No ADMIN_PASSWORD set. Run create_admin.py manually.')
    else:
        print(f'Admin user \"{admin.username}\" already exists.')

print('Database ready.')
"

echo "=== Starting Gunicorn ==="
exec gunicorn \
    --bind 0.0.0.0:5000 \
    --workers 2 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile - \
    "app:create_app()"

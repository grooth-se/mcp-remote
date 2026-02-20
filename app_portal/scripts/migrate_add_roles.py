#!/usr/bin/env python3
"""Migration: Add per-app role columns to applications and user_permissions tables."""

import sys
import os
import json
import sqlite3

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.extensions import db

# Role definitions per app
APP_ROLES = {
    'durabler2': {
        'available_roles': json.dumps({
            'operator': 'Operator',
            'engineer': 'Test Engineer',
            'approver': 'Approver',
            'admin': 'Administrator',
        }),
        'default_role': 'operator',
    },
}


def migrate():
    app = create_app()
    with app.app_context():
        db_path = app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check which columns already exist
        cursor.execute("PRAGMA table_info(applications)")
        app_cols = {row[1] for row in cursor.fetchall()}

        cursor.execute("PRAGMA table_info(user_permissions)")
        perm_cols = {row[1] for row in cursor.fetchall()}

        # Add columns if missing
        if 'available_roles' not in app_cols:
            cursor.execute("ALTER TABLE applications ADD COLUMN available_roles TEXT")
            print("  Added: applications.available_roles")

        if 'default_role' not in app_cols:
            cursor.execute("ALTER TABLE applications ADD COLUMN default_role VARCHAR(50)")
            print("  Added: applications.default_role")

        if 'role' not in perm_cols:
            cursor.execute("ALTER TABLE user_permissions ADD COLUMN role VARCHAR(50)")
            print("  Added: user_permissions.role")

        conn.commit()

        # Seed role data for apps that have roles
        for app_code, role_data in APP_ROLES.items():
            cursor.execute(
                "UPDATE applications SET available_roles = ?, default_role = ? WHERE app_code = ?",
                (role_data['available_roles'], role_data['default_role'], app_code),
            )
            if cursor.rowcount:
                print(f"  Seeded roles for: {app_code}")

        conn.commit()
        conn.close()
        print("\nMigration complete.")


if __name__ == '__main__':
    migrate()

#!/usr/bin/env python3
"""Create the first admin user for the portal."""

import sys
import os
import getpass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.extensions import db
from app.models.user import User


def create_admin():
    app = create_app()
    with app.app_context():
        db.create_all()

        # Check for existing admin
        existing = User.query.filter_by(is_admin=True).first()
        if existing:
            print(f"Admin user already exists: {existing.username}")
            resp = input("Create another admin? (y/N): ").strip().lower()
            if resp != 'y':
                return

        print("\n--- Create Admin User ---\n")
        username = input("Username: ").strip()
        if not username:
            print("Error: Username required.")
            return

        if User.query.filter_by(username=username).first():
            print(f"Error: User '{username}' already exists.")
            return

        display_name = input("Display name (optional): ").strip() or None
        email = input("Email (optional): ").strip() or None

        while True:
            password = getpass.getpass("Password (min 8 chars): ")
            if len(password) < 8:
                print("Password too short. Minimum 8 characters.")
                continue
            confirm = getpass.getpass("Confirm password: ")
            if password != confirm:
                print("Passwords don't match.")
                continue
            break

        user = User(
            username=username,
            display_name=display_name,
            email=email,
            is_admin=True,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        print(f"\nAdmin user '{username}' created successfully.")


if __name__ == '__main__':
    create_admin()

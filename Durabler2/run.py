#!/usr/bin/env python3
"""Application entry point."""
import os
from app import create_app, db
from app.models import User

# Get config from environment or use development
config_name = os.environ.get('FLASK_CONFIG') or 'development'
app = create_app(config_name)


@app.shell_context_processor
def make_shell_context():
    """Make database and models available in flask shell."""
    return {'db': db, 'User': User}


@app.cli.command()
def create_admin():
    """Create an admin user."""
    import getpass

    username = input('Admin username: ')
    password = getpass.getpass('Admin password: ')

    if User.query.filter_by(username=username).first():
        print(f'User {username} already exists!')
        return

    user = User(username=username, role='admin')
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    print(f'Admin user {username} created successfully!')


@app.cli.command()
def init_db():
    """Initialize the database."""
    db.create_all()
    print('Database initialized!')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)

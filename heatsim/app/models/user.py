"""User model for authentication."""
from datetime import datetime
from functools import wraps
from flask import flash, redirect, url_for
from flask_login import UserMixin, current_user
from werkzeug.security import generate_password_hash, check_password_hash

from app.extensions import db, login_manager


# User roles (simplified for initial deployment)
ROLE_ENGINEER = 'engineer'
ROLE_ADMIN = 'admin'

ROLES = [ROLE_ENGINEER, ROLE_ADMIN]
ROLE_LABELS = {
    ROLE_ENGINEER: 'Materials Engineer',
    ROLE_ADMIN: 'Administrator',
}


class User(UserMixin, db.Model):
    """User model for authentication.

    Attributes
    ----------
    id : int
        Primary key
    username : str
        Unique username for login
    password_hash : str
        Hashed password
    role : str
        User role: 'engineer', 'admin'
    created_at : datetime
        Account creation timestamp
    last_login : datetime
        Last login timestamp
    """
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256))
    role = db.Column(db.String(20), default=ROLE_ENGINEER)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)

    @property
    def is_admin(self) -> bool:
        """Check if user is administrator."""
        return self.role == ROLE_ADMIN

    @property
    def role_label(self) -> str:
        """Get human-readable role label."""
        return ROLE_LABELS.get(self.role, self.role)

    def set_password(self, password: str) -> None:
        """Hash and store password."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Verify password against stored hash."""
        return check_password_hash(self.password_hash, password)

    def update_last_login(self) -> None:
        """Update last login timestamp."""
        self.last_login = datetime.utcnow()

    def __repr__(self) -> str:
        return f'<User {self.username}>'


@login_manager.user_loader
def load_user(user_id: str) -> User | None:
    """Load user by ID for Flask-Login."""
    return db.session.get(User, int(user_id))


def admin_required(f):
    """Decorator to require admin role."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        if not current_user.is_admin:
            flash('Administrator access required.', 'danger')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated_function

"""User model for authentication."""
from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from app.extensions import db, login_manager


class User(UserMixin, db.Model):
    """User model for authentication and audit trail.

    Attributes
    ----------
    id : int
        Primary key
    username : str
        Unique username for login
    password_hash : str
        Hashed password
    role : str
        User role: 'operator', 'reviewer', 'admin'
    is_active : bool
        Whether user account is active
    created_at : datetime
        Account creation timestamp
    """
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256))
    role = db.Column(db.String(20), default='operator')  # operator, reviewer, admin
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    test_records = db.relationship('TestRecord', backref='operator', lazy='dynamic',
                                   foreign_keys='TestRecord.operator_id')

    def set_password(self, password: str) -> None:
        """Hash and store password."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Verify password against stored hash."""
        return check_password_hash(self.password_hash, password)

    def __repr__(self) -> str:
        return f'<User {self.username}>'


@login_manager.user_loader
def load_user(user_id: str) -> User | None:
    """Load user by ID for Flask-Login."""
    return User.query.get(int(user_id))

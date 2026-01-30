"""User model for authentication and approval workflow."""
from datetime import datetime
from functools import wraps
from flask import flash, redirect, url_for
from flask_login import UserMixin, current_user
from werkzeug.security import generate_password_hash, check_password_hash

from app.extensions import db, login_manager


# User roles
ROLE_OPERATOR = 'operator'
ROLE_ENGINEER = 'engineer'
ROLE_APPROVER = 'approver'
ROLE_ADMIN = 'admin'

ROLES = [ROLE_OPERATOR, ROLE_ENGINEER, ROLE_APPROVER, ROLE_ADMIN]
ROLE_LABELS = {
    ROLE_OPERATOR: 'Operator',
    ROLE_ENGINEER: 'Test Engineer',
    ROLE_APPROVER: 'Approver',
    ROLE_ADMIN: 'Administrator',
}


class User(UserMixin, db.Model):
    """User model for authentication, approval workflow, and audit trail.

    Attributes
    ----------
    id : int
        Primary key
    user_id : str
        Unique user identifier (e.g., DUR-ENG-001) for audit trail
    username : str
        Unique username for login
    password_hash : str
        Hashed password
    full_name : str
        Full name for display and signatures
    email : str
        Email address (optional)
    role : str
        User role: 'operator', 'engineer', 'approver', 'admin'
    can_approve : bool
        Whether user can approve reports (derived from role)
    is_active : bool
        Whether user account is active
    created_at : datetime
        Account creation timestamp
    last_login : datetime
        Last successful login timestamp
    """
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(20), unique=True, index=True)  # DUR-ENG-001
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256))
    full_name = db.Column(db.String(120))  # For signature display
    email = db.Column(db.String(120))
    role = db.Column(db.String(20), default=ROLE_OPERATOR)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)

    # Relationships
    test_records = db.relationship('TestRecord', backref='operator', lazy='dynamic',
                                   foreign_keys='TestRecord.operator_id')

    @property
    def can_approve(self) -> bool:
        """Check if user can approve reports."""
        return self.role in [ROLE_APPROVER, ROLE_ADMIN]

    @property
    def can_submit(self) -> bool:
        """Check if user can submit reports for approval."""
        return self.role in [ROLE_ENGINEER, ROLE_APPROVER, ROLE_ADMIN]

    @property
    def is_admin(self) -> bool:
        """Check if user is administrator."""
        return self.role == ROLE_ADMIN

    @property
    def role_label(self) -> str:
        """Get human-readable role label."""
        return ROLE_LABELS.get(self.role, self.role)

    @staticmethod
    def generate_user_id(role: str) -> str:
        """Generate next user ID for a role.

        Format: DUR-XXX-NNN where XXX is role prefix and NNN is sequence number.
        """
        prefix_map = {
            ROLE_OPERATOR: 'OPR',
            ROLE_ENGINEER: 'ENG',
            ROLE_APPROVER: 'APR',
            ROLE_ADMIN: 'ADM',
        }
        prefix = prefix_map.get(role, 'USR')

        # Find highest existing number for this prefix
        pattern = f'DUR-{prefix}-%'
        existing = User.query.filter(User.user_id.like(pattern)).all()
        if existing:
            numbers = []
            for u in existing:
                try:
                    num = int(u.user_id.split('-')[-1])
                    numbers.append(num)
                except (ValueError, IndexError):
                    pass
            next_num = max(numbers) + 1 if numbers else 1
        else:
            next_num = 1

        return f'DUR-{prefix}-{next_num:03d}'

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
        return f'<User {self.user_id or self.username}>'


@login_manager.user_loader
def load_user(user_id: str) -> User | None:
    """Load user by ID for Flask-Login."""
    return User.query.get(int(user_id))


# Role-based access control decorators

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


def approver_required(f):
    """Decorator to require approver or admin role."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        if not current_user.can_approve:
            flash('Approver access required.', 'danger')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated_function


def engineer_required(f):
    """Decorator to require engineer, approver, or admin role."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        if not current_user.can_submit:
            flash('Test Engineer access required.', 'danger')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated_function

from datetime import datetime, timezone
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import db


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    display_name = db.Column(db.String(120))
    email = db.Column(db.String(120))
    is_admin = db.Column(db.Boolean, default=False)
    is_active_user = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    last_login = db.Column(db.DateTime, nullable=True)
    password_changed_at = db.Column(db.DateTime, nullable=True)

    # Relationships
    permissions = db.relationship('UserPermission', back_populates='user',
                                  foreign_keys='UserPermission.user_id',
                                  cascade='all, delete-orphan')
    sessions = db.relationship('UserSession', back_populates='user',
                               foreign_keys='UserSession.user_id',
                               cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        self.password_changed_at = datetime.now(timezone.utc)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_active(self):
        return self.is_active_user

    def has_app_permission(self, app_code):
        """Check if user has permission for a specific app."""
        if self.is_admin:
            return True
        from app.models.application import Application
        app = Application.query.filter_by(app_code=app_code, is_active=True).first()
        if not app:
            return False
        from app.models.permission import UserPermission
        return UserPermission.query.filter_by(user_id=self.id, app_id=app.id).first() is not None

    def get_permitted_apps(self):
        """Get list of apps this user can access."""
        from app.models.application import Application
        if self.is_admin:
            return Application.query.filter_by(is_active=True).order_by(Application.display_order).all()
        from app.models.permission import UserPermission
        app_ids = [p.app_id for p in UserPermission.query.filter_by(user_id=self.id).all()]
        return Application.query.filter(
            Application.id.in_(app_ids),
            Application.is_active == True  # noqa: E712
        ).order_by(Application.display_order).all()

    def __repr__(self):
        return f'<User {self.username}>'

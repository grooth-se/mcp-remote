import json
from datetime import datetime, timezone
from app.extensions import db


class Application(db.Model):
    __tablename__ = 'applications'

    id = db.Column(db.Integer, primary_key=True)
    app_code = db.Column(db.String(50), unique=True, nullable=False)
    app_name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text)
    internal_url = db.Column(db.String(256), nullable=False)
    icon = db.Column(db.String(50), default='bi-app')
    display_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    requires_gpu = db.Column(db.Boolean, default=False)
    available_roles = db.Column(db.Text, nullable=True)
    default_role = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    permissions = db.relationship('UserPermission', back_populates='app', cascade='all, delete-orphan')

    def get_available_roles(self):
        """Return available roles as dict {value: label}, or empty dict.

        Supports both formats:
        - dict: {"operator": "Operator", "engineer": "Test Engineer"}
        - list (legacy): ["admin", "engineer"] -> {"admin": "admin", ...}
        """
        if not self.available_roles:
            return {}
        try:
            data = json.loads(self.available_roles)
            if isinstance(data, dict):
                return data
            if isinstance(data, list):
                return {v: v for v in data}
            return {}
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_available_roles(self, roles):
        """Set available roles from a dict {value: label} or None to clear."""
        if roles:
            self.available_roles = json.dumps(roles)
        else:
            self.available_roles = None

    def __repr__(self):
        return f'<Application {self.app_code}>'

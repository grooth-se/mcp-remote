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
        """Return list of available roles, or empty list if none configured."""
        if not self.available_roles:
            return []
        try:
            return json.loads(self.available_roles)
        except (json.JSONDecodeError, TypeError):
            return []

    def set_available_roles(self, roles_list):
        """Set available roles from a list of strings."""
        if roles_list:
            self.available_roles = json.dumps(roles_list)
        else:
            self.available_roles = None

    def __repr__(self):
        return f'<Application {self.app_code}>'

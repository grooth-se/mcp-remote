"""Audit log model for tracking user actions."""
import json
from datetime import datetime

from app.extensions import db


# Action constants
ACTION_LOGIN = 'login'
ACTION_LOGOUT = 'logout'
ACTION_CREATE_USER = 'create_user'
ACTION_DELETE_USER = 'delete_user'
ACTION_UPDATE_USER = 'update_user'
ACTION_RUN_SIMULATION = 'run_simulation'
ACTION_DELETE_SIMULATION = 'delete_simulation'
ACTION_CREATE_SIMULATION = 'create_simulation'
ACTION_UPLOAD_DATA = 'upload_data'
ACTION_DELETE_DATA = 'delete_data'

ACTION_LABELS = {
    ACTION_LOGIN: 'Login',
    ACTION_LOGOUT: 'Logout',
    ACTION_CREATE_USER: 'Create User',
    ACTION_DELETE_USER: 'Delete User',
    ACTION_UPDATE_USER: 'Update User',
    ACTION_RUN_SIMULATION: 'Run Simulation',
    ACTION_DELETE_SIMULATION: 'Delete Simulation',
    ACTION_CREATE_SIMULATION: 'Create Simulation',
    ACTION_UPLOAD_DATA: 'Upload Data',
    ACTION_DELETE_DATA: 'Delete Data',
}

ACTION_BADGES = {
    ACTION_LOGIN: 'success',
    ACTION_LOGOUT: 'secondary',
    ACTION_CREATE_USER: 'primary',
    ACTION_DELETE_USER: 'danger',
    ACTION_UPDATE_USER: 'info',
    ACTION_RUN_SIMULATION: 'warning',
    ACTION_DELETE_SIMULATION: 'danger',
    ACTION_CREATE_SIMULATION: 'primary',
    ACTION_UPLOAD_DATA: 'info',
    ACTION_DELETE_DATA: 'danger',
}


class AuditLog(db.Model):
    """Tracks user actions for audit purposes."""
    __tablename__ = 'audit_logs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    username = db.Column(db.String(80), nullable=False)
    action = db.Column(db.String(50), nullable=False, index=True)
    resource_type = db.Column(db.String(50), nullable=True)
    resource_id = db.Column(db.Integer, nullable=True)
    resource_name = db.Column(db.String(200), nullable=True)
    details_json = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    user = db.relationship('User', backref=db.backref('audit_entries', lazy='dynamic'))

    @property
    def action_label(self):
        return ACTION_LABELS.get(self.action, self.action)

    @property
    def action_badge(self):
        return ACTION_BADGES.get(self.action, 'secondary')

    @property
    def details(self):
        if self.details_json:
            return json.loads(self.details_json)
        return None

    @classmethod
    def log(cls, action, resource_type=None, resource_id=None,
            resource_name=None, details=None):
        """Create an audit log entry.

        Auto-fills user and IP from request context.
        """
        from flask import request
        from flask_login import current_user

        username = 'system'
        user_id = None
        if current_user and hasattr(current_user, 'id') and current_user.is_authenticated:
            username = current_user.username
            user_id = current_user.id

        ip_address = None
        try:
            ip_address = request.remote_addr
        except RuntimeError:
            pass

        entry = cls(
            user_id=user_id,
            username=username,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_name=resource_name,
            details_json=json.dumps(details) if details else None,
            ip_address=ip_address,
        )
        db.session.add(entry)
        db.session.commit()
        return entry

from datetime import datetime, timezone
from app.extensions import db


class AccessLog(db.Model):
    __tablename__ = 'access_log'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    app_id = db.Column(db.Integer, db.ForeignKey('applications.id'), nullable=True)
    action = db.Column(db.String(50))  # login, logout, access_app, denied
    ip_address = db.Column(db.String(45))
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    details = db.Column(db.Text)

    user = db.relationship('User', foreign_keys=[user_id])
    app = db.relationship('Application', foreign_keys=[app_id])


class AuditLog(db.Model):
    __tablename__ = 'audit_log'

    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    action = db.Column(db.String(100), nullable=False)
    target_type = db.Column(db.String(50))  # user, app, permission
    target_id = db.Column(db.Integer)
    old_value = db.Column(db.Text)
    new_value = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    admin = db.relationship('User', foreign_keys=[admin_id])

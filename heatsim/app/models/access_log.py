"""Portal access log model."""
from datetime import datetime, timezone
from app.extensions import db


class AccessLog(db.Model):
    __tablename__ = 'access_log'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    app_id = db.Column(db.Integer, db.ForeignKey('applications.id'), nullable=True)
    action = db.Column(db.String(50))
    ip_address = db.Column(db.String(45))
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    details = db.Column(db.Text)

    user = db.relationship('User', foreign_keys=[user_id])
    app = db.relationship('Application', foreign_keys=[app_id])

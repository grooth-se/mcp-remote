"""Notification model (Phase 7B)."""

from datetime import datetime, timezone
from app.extensions import db


class Notification(db.Model):
    __tablename__ = 'notifications'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    notification_type = db.Column(db.String(50), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.String(500))
    link = db.Column(db.String(300))
    icon = db.Column(db.String(50), default='bi-bell')
    read = db.Column(db.Boolean, default=False)
    entity_type = db.Column(db.String(50), nullable=True)
    entity_id = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    user = db.relationship('User', backref='notifications')
    company = db.relationship('Company', backref='notifications')

    __table_args__ = (
        db.Index('ix_notification_user_read', 'user_id', 'read'),
        db.Index('ix_notification_company_type', 'company_id', 'notification_type'),
    )

    def __repr__(self):
        return f'<Notification {self.title} ({self.notification_type})>'

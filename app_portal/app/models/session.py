from datetime import datetime, timezone
from app.extensions import db


class UserSession(db.Model):
    __tablename__ = 'sessions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    token = db.Column(db.String(512), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at = db.Column(db.DateTime, nullable=False)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(256))
    is_active = db.Column(db.Boolean, default=True)

    # Relationships
    user = db.relationship('User', back_populates='sessions')

    @property
    def is_expired(self):
        return datetime.now(timezone.utc) > self.expires_at

    def __repr__(self):
        return f'<UserSession user={self.user_id} active={self.is_active}>'

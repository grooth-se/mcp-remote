"""Portal user permission model."""
from datetime import datetime, timezone
from app.extensions import db


class UserPermission(db.Model):
    __tablename__ = 'user_permissions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    app_id = db.Column(db.Integer, db.ForeignKey('applications.id', ondelete='CASCADE'), nullable=False)
    granted_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    granted_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'app_id', name='uq_user_app'),
    )

    user = db.relationship('User', back_populates='permissions', foreign_keys=[user_id])
    app = db.relationship('Application', back_populates='permissions')
    granter = db.relationship('User', foreign_keys=[granted_by])

    def __repr__(self):
        return f'<UserPermission user={self.user_id} app={self.app_id}>'

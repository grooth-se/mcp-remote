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
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    permissions = db.relationship('UserPermission', back_populates='app', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Application {self.app_code}>'

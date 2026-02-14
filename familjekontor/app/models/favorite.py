"""UserFavorite model (Phase 7D)."""

from datetime import datetime

from app.extensions import db


class UserFavorite(db.Model):
    __tablename__ = 'user_favorites'
    __table_args__ = (
        db.Index('ix_favorite_user_order', 'user_id', 'sort_order'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    label = db.Column(db.String(100), nullable=False)
    url = db.Column(db.String(300), nullable=False)
    icon = db.Column(db.String(50), default='bi-star-fill')
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<UserFavorite {self.label}>'

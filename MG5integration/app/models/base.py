from datetime import datetime, timezone
from app.extensions import db


class TimestampMixin:
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )
    source = db.Column(db.String(20), default='excel')
    import_batch_id = db.Column(db.String(36), index=True)

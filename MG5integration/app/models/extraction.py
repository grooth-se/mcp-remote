from datetime import datetime, timezone
from app.extensions import db


class ExtractionLog(db.Model):
    """Track each import/extraction run."""
    __tablename__ = 'extraction_log'

    id = db.Column(db.Integer, primary_key=True)
    batch_id = db.Column(db.String(36), unique=True, index=True)
    started_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = db.Column(db.DateTime)
    source = db.Column(db.String(20), default='excel')
    status = db.Column(db.String(20), default='running')  # running, success, failed
    records_imported = db.Column(db.Integer, default=0)
    errors = db.Column(db.Text)
    details = db.Column(db.Text)  # JSON: per-table counts

    def to_dict(self):
        return {
            'id': self.id,
            'batch_id': self.batch_id,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'source': self.source,
            'status': self.status,
            'records_imported': self.records_imported,
            'errors': self.errors,
            'details': self.details,
        }

from datetime import datetime, timezone
from app.extensions import db


class Document(db.Model):
    __tablename__ = 'documents'

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    document_type = db.Column(db.String(50))  # invoice, certificate, contract, annual_report
    file_name = db.Column(db.String(300))
    file_path = db.Column(db.String(500))
    mime_type = db.Column(db.String(100))
    description = db.Column(db.String(500), nullable=True)
    expiry_date = db.Column(db.Date)
    reminder_date = db.Column(db.Date)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    company = db.relationship('Company', backref='documents')
    uploader = db.relationship('User', foreign_keys=[uploaded_by])

    def __repr__(self):
        return f'<Document {self.file_name}>'

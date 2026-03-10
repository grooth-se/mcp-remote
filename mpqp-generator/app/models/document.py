from datetime import datetime
from app import db


class Document(db.Model):
    __tablename__ = 'documents'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'))
    document_type = db.Column(db.String(50))  # MPQP, MPS, ITP, SPEC, DRAWING, CONTRACT
    file_name = db.Column(db.String(300), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    file_format = db.Column(db.String(10))  # PDF, DOCX, XLSX
    file_size = db.Column(db.Integer)  # bytes
    page_count = db.Column(db.Integer)
    extracted_text = db.Column(db.Text)
    metadata_ = db.Column('metadata', db.JSON, default=dict)
    indexed_at = db.Column(db.DateTime)
    embedding_ids = db.Column(db.JSON, default=list)  # References to vector DB chunks
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    DOCUMENT_TYPES = [
        ('MPQP', 'Manufacturing Procedure Quality Plan'),
        ('MPS', 'Manufacturing Procedure Specification'),
        ('ITP', 'Inspection and Test Plan'),
        ('SPEC', 'Customer Specification'),
        ('DRAWING', 'Drawing'),
        ('CONTRACT', 'Contract'),
        ('STANDARD', 'Standard'),
        ('OTHER', 'Other'),
    ]

    FORMAT_EXTENSIONS = {
        '.pdf': 'PDF',
        '.docx': 'DOCX',
        '.doc': 'DOC',
        '.xlsx': 'XLSX',
        '.xls': 'XLS',
    }

    def __repr__(self):
        return f'<Document {self.file_name}>'

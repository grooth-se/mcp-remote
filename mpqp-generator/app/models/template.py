from datetime import datetime
from app import db


class Template(db.Model):
    __tablename__ = 'templates'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    document_type = db.Column(db.String(10), nullable=False)  # MPQP, MPS, ITP
    format = db.Column(db.String(10), nullable=False)  # DOCX, XLSX
    file_path = db.Column(db.String(500), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=True)
    structure = db.Column(db.JSON, default=dict)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    customer = db.relationship('Customer', backref='templates')

    DOCUMENT_TYPES = [('MPQP', 'MPQP'), ('MPS', 'MPS'), ('ITP', 'ITP')]
    FORMATS = [('DOCX', 'Word'), ('XLSX', 'Excel')]

    def __repr__(self):
        return f'<Template {self.name} ({self.document_type})>'

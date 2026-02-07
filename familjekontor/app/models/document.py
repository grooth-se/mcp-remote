from datetime import datetime, timezone
from app.extensions import db


class Document(db.Model):
    __tablename__ = 'documents'

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    document_type = db.Column(db.String(50))  # faktura, avtal, intyg, arsredovisning, kvitto, ovrigt
    file_name = db.Column(db.String(300))
    file_path = db.Column(db.String(500))
    mime_type = db.Column(db.String(100))
    description = db.Column(db.String(500), nullable=True)
    expiry_date = db.Column(db.Date)
    reminder_date = db.Column(db.Date)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Links to accounting entities (Phase 4D)
    verification_id = db.Column(db.Integer, db.ForeignKey('verifications.id'), nullable=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('supplier_invoices.id'), nullable=True)
    customer_invoice_id = db.Column(db.Integer, db.ForeignKey('customer_invoices.id'), nullable=True)

    company = db.relationship('Company', backref='documents')
    uploader = db.relationship('User', foreign_keys=[uploaded_by])
    verification = db.relationship('Verification', backref='documents',
                                    foreign_keys=[verification_id])
    supplier_invoice = db.relationship('SupplierInvoice', backref='attached_documents',
                                       foreign_keys=[invoice_id])
    customer_invoice = db.relationship('CustomerInvoice', backref='attached_documents',
                                       foreign_keys=[customer_invoice_id])

    def __repr__(self):
        return f'<Document {self.file_name}>'

from datetime import datetime, timezone
from app.extensions import db


class PaymentFile(db.Model):
    __tablename__ = 'payment_files'

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    bank_account_id = db.Column(db.Integer, db.ForeignKey('bank_accounts.id'), nullable=False)
    batch_reference = db.Column(db.String(50), nullable=False)
    file_format = db.Column(db.String(20), nullable=False)  # pain001, bankgirot
    status = db.Column(db.String(20), default='draft')  # draft, generated, uploaded, confirmed, cancelled
    execution_date = db.Column(db.Date, nullable=False)
    total_amount = db.Column(db.Numeric(15, 2), default=0)
    currency = db.Column(db.String(3), default='SEK')
    number_of_transactions = db.Column(db.Integer, default=0)
    file_path = db.Column(db.String(500), nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    confirmed_at = db.Column(db.DateTime, nullable=True)
    confirmed_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    company = db.relationship('Company', backref='payment_files')
    bank_account = db.relationship('BankAccount', backref='payment_files')
    creator = db.relationship('User', foreign_keys=[created_by])
    confirmer = db.relationship('User', foreign_keys=[confirmed_by])
    instructions = db.relationship('PaymentInstruction', backref='payment_file',
                                   cascade='all, delete-orphan')

    def __repr__(self):
        return f'<PaymentFile {self.batch_reference} ({self.status})>'


class PaymentInstruction(db.Model):
    __tablename__ = 'payment_instructions'

    id = db.Column(db.Integer, primary_key=True)
    payment_file_id = db.Column(db.Integer, db.ForeignKey('payment_files.id'), nullable=False)
    supplier_invoice_id = db.Column(db.Integer, db.ForeignKey('supplier_invoices.id'), nullable=False)
    amount = db.Column(db.Numeric(15, 2), nullable=False)
    currency = db.Column(db.String(3), default='SEK')
    payment_method = db.Column(db.String(20), nullable=False)  # bankgiro, plusgiro, iban
    creditor_account = db.Column(db.String(34), nullable=False)
    creditor_bic = db.Column(db.String(11), nullable=True)
    creditor_name = db.Column(db.String(200), nullable=False)
    remittance_info = db.Column(db.String(140), nullable=True)
    end_to_end_id = db.Column(db.String(35), nullable=True)
    status = db.Column(db.String(20), default='pending')  # pending, paid, failed

    supplier_invoice = db.relationship('SupplierInvoice', backref='payment_instructions')

    __table_args__ = (
        db.UniqueConstraint('payment_file_id', 'supplier_invoice_id',
                            name='uq_payment_file_invoice'),
    )

    def __repr__(self):
        return f'<PaymentInstruction {self.creditor_name} {self.amount}>'

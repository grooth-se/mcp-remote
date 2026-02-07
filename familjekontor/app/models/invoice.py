from datetime import datetime, timezone
from app.extensions import db


class Supplier(db.Model):
    __tablename__ = 'suppliers'

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    org_number = db.Column(db.String(20))
    default_account = db.Column(db.String(10))
    payment_terms = db.Column(db.Integer, default=30)
    bankgiro = db.Column(db.String(20))
    plusgiro = db.Column(db.String(20))
    iban = db.Column(db.String(34))
    bic = db.Column(db.String(11))
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    invoices = db.relationship('SupplierInvoice', backref='supplier', lazy='dynamic')
    company = db.relationship('Company', backref='suppliers')

    def __repr__(self):
        return f'<Supplier {self.name}>'


class SupplierInvoice(db.Model):
    __tablename__ = 'supplier_invoices'

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'), nullable=False)
    invoice_number = db.Column(db.String(50))
    invoice_date = db.Column(db.Date)
    due_date = db.Column(db.Date)
    amount_excl_vat = db.Column(db.Numeric(15, 2))
    vat_amount = db.Column(db.Numeric(15, 2))
    total_amount = db.Column(db.Numeric(15, 2))
    currency = db.Column(db.String(3), default='SEK')
    status = db.Column(db.String(20), default='pending')  # pending, approved, paid, cancelled
    verification_id = db.Column(db.Integer, db.ForeignKey('verifications.id'), nullable=True)
    document_id = db.Column(db.Integer, db.ForeignKey('documents.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    company = db.relationship('Company', backref='supplier_invoices')
    verification = db.relationship('Verification')

    def __repr__(self):
        return f'<SupplierInvoice {self.invoice_number}>'


class Customer(db.Model):
    __tablename__ = 'customers'

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    org_number = db.Column(db.String(20))
    country = db.Column(db.String(2), default='SE')
    vat_number = db.Column(db.String(20))
    address = db.Column(db.String(300))
    postal_code = db.Column(db.String(10))
    city = db.Column(db.String(100))
    email = db.Column(db.String(120))
    payment_terms = db.Column(db.Integer, default=30)
    default_currency = db.Column(db.String(3), default='SEK')
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    invoices = db.relationship('CustomerInvoice', backref='customer', lazy='dynamic')
    company = db.relationship('Company', backref='customers')

    def __repr__(self):
        return f'<Customer {self.name}>'


class CustomerInvoice(db.Model):
    __tablename__ = 'customer_invoices'

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False)
    invoice_number = db.Column(db.String(50), nullable=False)
    invoice_date = db.Column(db.Date, nullable=False)
    due_date = db.Column(db.Date, nullable=False)
    currency = db.Column(db.String(3), default='SEK')
    exchange_rate = db.Column(db.Numeric(10, 6), default=1.0)
    amount_excl_vat = db.Column(db.Numeric(15, 2))
    vat_amount = db.Column(db.Numeric(15, 2))
    total_amount = db.Column(db.Numeric(15, 2))
    vat_type = db.Column(db.String(20))  # standard, reverse_charge, export
    status = db.Column(db.String(20), default='draft')  # draft, sent, paid, overdue, cancelled
    verification_id = db.Column(db.Integer, db.ForeignKey('verifications.id'), nullable=True)
    sent_at = db.Column(db.DateTime)
    paid_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    company = db.relationship('Company', backref='customer_invoices')
    verification = db.relationship('Verification')

    def __repr__(self):
        return f'<CustomerInvoice {self.invoice_number}>'

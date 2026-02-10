from datetime import datetime, timezone
from app.extensions import db


class RecurringInvoiceTemplate(db.Model):
    __tablename__ = 'recurring_invoice_templates'

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    currency = db.Column(db.String(3), default='SEK')
    vat_type = db.Column(db.String(20), default='standard')
    interval = db.Column(db.String(20), nullable=False)  # monthly, quarterly, yearly
    payment_terms = db.Column(db.Integer, default=30)
    start_date = db.Column(db.Date, nullable=False)
    next_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=True)
    active = db.Column(db.Boolean, default=True)
    last_generated_at = db.Column(db.DateTime, nullable=True)
    invoices_generated = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    company = db.relationship('Company', backref='recurring_templates')
    customer = db.relationship('Customer', backref='recurring_templates')
    line_items = db.relationship('RecurringLineItem', backref='template',
                                 order_by='RecurringLineItem.line_number',
                                 cascade='all, delete-orphan')

    def __repr__(self):
        return f'<RecurringInvoiceTemplate {self.name}>'


class RecurringLineItem(db.Model):
    __tablename__ = 'recurring_line_items'

    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(db.Integer, db.ForeignKey('recurring_invoice_templates.id',
                            ondelete='CASCADE'), nullable=False)
    line_number = db.Column(db.Integer, nullable=False)
    description = db.Column(db.String(500), nullable=False)
    quantity = db.Column(db.Numeric(10, 2), default=1)
    unit = db.Column(db.String(20), default='st')
    unit_price = db.Column(db.Numeric(15, 2), nullable=False)
    vat_rate = db.Column(db.Numeric(5, 2), default=25)

    def __repr__(self):
        return f'<RecurringLineItem {self.line_number} {self.description}>'

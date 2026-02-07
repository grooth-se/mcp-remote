from datetime import datetime, timezone
from app.extensions import db


class Company(db.Model):
    __tablename__ = 'companies'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    org_number = db.Column(db.String(20), unique=True, nullable=False)
    company_type = db.Column(db.String(10), nullable=False)  # AB, HB
    accounting_standard = db.Column(db.String(10), default='K2')  # K2, K3
    fiscal_year_start = db.Column(db.Integer, default=1)  # Month
    vat_period = db.Column(db.String(20), default='quarterly')
    base_currency = db.Column(db.String(3), default='SEK')
    parent_company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True)
    street_address = db.Column(db.String(300), nullable=True)
    postal_code = db.Column(db.String(10), nullable=True)
    city = db.Column(db.String(100), nullable=True)
    country = db.Column(db.String(100), default='Sverige')
    logo_path = db.Column(db.String(500), nullable=True)
    theme_color = db.Column(db.String(7), nullable=True)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    parent = db.relationship('Company', remote_side=[id], backref='subsidiaries')
    fiscal_years = db.relationship('FiscalYear', backref='company', lazy='dynamic')
    accounts = db.relationship('Account', backref='company', lazy='dynamic')

    def __repr__(self):
        return f'<Company {self.name} ({self.org_number})>'

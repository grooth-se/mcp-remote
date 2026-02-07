from datetime import datetime, timezone
from app.extensions import db


class FiscalYear(db.Model):
    __tablename__ = 'fiscal_years'

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), default='open')  # open, closed, archived

    verifications = db.relationship('Verification', backref='fiscal_year', lazy='dynamic')

    __table_args__ = (
        db.UniqueConstraint('company_id', 'year', name='uq_company_fiscal_year'),
    )

    def __repr__(self):
        return f'<FiscalYear {self.year} ({self.status})>'


class Account(db.Model):
    __tablename__ = 'accounts'

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    account_number = db.Column(db.String(10), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    account_type = db.Column(db.String(20), nullable=False)  # asset, liability, equity, revenue, expense
    vat_code = db.Column(db.String(10), nullable=True)
    active = db.Column(db.Boolean, default=True)

    __table_args__ = (
        db.UniqueConstraint('company_id', 'account_number', name='uq_company_account'),
    )

    def __repr__(self):
        return f'<Account {self.account_number} {self.name}>'


class Verification(db.Model):
    __tablename__ = 'verifications'

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    fiscal_year_id = db.Column(db.Integer, db.ForeignKey('fiscal_years.id'), nullable=False)
    verification_number = db.Column(db.Integer, nullable=False)
    verification_date = db.Column(db.Date, nullable=False)
    description = db.Column(db.String(500))
    verification_type = db.Column(db.String(20))  # supplier, customer, bank, salary, manual
    source = db.Column(db.String(50))  # 'manual', 'sie_import', etc.
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    rows = db.relationship('VerificationRow', backref='verification', lazy='select',
                           cascade='all, delete-orphan')
    creator = db.relationship('User', foreign_keys=[created_by])

    __table_args__ = (
        db.UniqueConstraint('company_id', 'fiscal_year_id', 'verification_number',
                            name='uq_company_fy_vernum'),
    )

    @property
    def total_debit(self):
        return sum(r.debit for r in self.rows)

    @property
    def total_credit(self):
        return sum(r.credit for r in self.rows)

    @property
    def is_balanced(self):
        return abs(self.total_debit - self.total_credit) < 0.01

    def __repr__(self):
        return f'<Verification #{self.verification_number} {self.verification_date}>'


class VerificationRow(db.Model):
    __tablename__ = 'verification_rows'

    id = db.Column(db.Integer, primary_key=True)
    verification_id = db.Column(db.Integer, db.ForeignKey('verifications.id'), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=False)
    debit = db.Column(db.Numeric(15, 2), default=0)
    credit = db.Column(db.Numeric(15, 2), default=0)
    description = db.Column(db.String(200))
    cost_center = db.Column(db.String(50))

    account = db.relationship('Account')

    def __repr__(self):
        return f'<VerificationRow {self.account.account_number if self.account else "?"} D:{self.debit} C:{self.credit}>'

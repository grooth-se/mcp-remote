from datetime import datetime, timezone
from app.extensions import db


class BankAccount(db.Model):
    __tablename__ = 'bank_accounts'

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    bank_name = db.Column(db.String(100), nullable=False)
    account_number = db.Column(db.String(30), nullable=False)
    clearing_number = db.Column(db.String(10), nullable=True)
    iban = db.Column(db.String(34), nullable=True)
    balance = db.Column(db.Numeric(15, 2), default=0)
    ledger_account = db.Column(db.String(10), default='1930')
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    company = db.relationship('Company', backref='bank_accounts')
    transactions = db.relationship('BankTransaction', backref='bank_account', lazy='dynamic')

    __table_args__ = (
        db.UniqueConstraint('company_id', 'account_number', name='uq_company_bank_account'),
    )

    def __repr__(self):
        return f'<BankAccount {self.bank_name} {self.account_number}>'


class BankTransaction(db.Model):
    __tablename__ = 'bank_transactions'

    id = db.Column(db.Integer, primary_key=True)
    bank_account_id = db.Column(db.Integer, db.ForeignKey('bank_accounts.id'), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    transaction_date = db.Column(db.Date, nullable=False)
    booking_date = db.Column(db.Date, nullable=True)
    description = db.Column(db.String(500), nullable=False)
    amount = db.Column(db.Numeric(15, 2), nullable=False)
    balance_after = db.Column(db.Numeric(15, 2), nullable=True)
    reference = db.Column(db.String(100), nullable=True)
    counterpart = db.Column(db.String(200), nullable=True)
    matched_verification_id = db.Column(db.Integer, db.ForeignKey('verifications.id'), nullable=True)
    status = db.Column(db.String(20), default='unmatched')  # unmatched, matched, ignored
    import_batch = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    company = db.relationship('Company', backref='bank_transactions')
    matched_verification = db.relationship('Verification', backref='bank_transactions')

    __table_args__ = (
        db.UniqueConstraint('bank_account_id', 'transaction_date', 'amount', 'description',
                            name='uq_bank_txn'),
    )

    def __repr__(self):
        return f'<BankTransaction {self.transaction_date} {self.amount}>'

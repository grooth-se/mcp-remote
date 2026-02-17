from datetime import datetime, timezone
from app.extensions import db


PORTFOLIO_TYPE_LABELS = {
    'aktiedepå': 'Aktiedepå',
    'isk': 'ISK',
    'kapitalforsakring': 'Kapitalförsäkring',
    'direkt': 'Direktinvesteringar',
}

INSTRUMENT_TYPE_LABELS = {
    'aktie': 'Aktie',
    'fond': 'Fond',
    'obligation': 'Obligation',
    'etf': 'ETF',
    'onoterad': 'Onoterad aktie',
    'lan': 'Lån',
    'foretagsobligation': 'Företagsobligation',
}

TRANSACTION_TYPE_LABELS = {
    'kop': 'Köp',
    'salj': 'Sälj',
    'utdelning': 'Utdelning',
    'ranta': 'Ränta',
    'avgift': 'Avgift',
    'insattning': 'Insättning',
    'uttag': 'Uttag',
    'utlan': 'Utlåning',
    'amortering': 'Amortering',
    'kupong': 'Kupongbetalning',
}


class InvestmentPortfolio(db.Model):
    __tablename__ = 'investment_portfolios'

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    portfolio_type = db.Column(db.String(30), default='aktiedepå')
    broker = db.Column(db.String(100), nullable=True)
    account_number = db.Column(db.String(50), nullable=True)
    currency = db.Column(db.String(3), default='SEK')
    ledger_account = db.Column(db.String(10), nullable=True)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    company = db.relationship('Company', backref='investment_portfolios')
    holdings = db.relationship('InvestmentHolding', backref='portfolio',
                               cascade='all, delete-orphan')
    transactions = db.relationship('InvestmentTransaction', backref='portfolio',
                                   cascade='all, delete-orphan')

    @property
    def portfolio_type_label(self):
        return PORTFOLIO_TYPE_LABELS.get(self.portfolio_type, self.portfolio_type)

    def __repr__(self):
        return f'<Portfolio {self.name} ({self.broker})>'


class InvestmentHolding(db.Model):
    __tablename__ = 'investment_holdings'

    id = db.Column(db.Integer, primary_key=True)
    portfolio_id = db.Column(db.Integer, db.ForeignKey('investment_portfolios.id'), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    isin = db.Column(db.String(12), nullable=True)
    name = db.Column(db.String(200), nullable=False)
    ticker = db.Column(db.String(20), nullable=True)
    instrument_type = db.Column(db.String(30), default='aktie')
    currency = db.Column(db.String(3), default='SEK')
    quantity = db.Column(db.Numeric(15, 4), default=0)
    average_cost = db.Column(db.Numeric(15, 4), default=0)
    total_cost = db.Column(db.Numeric(15, 2), default=0)
    current_price = db.Column(db.Numeric(15, 4), nullable=True)
    current_value = db.Column(db.Numeric(15, 2), nullable=True)
    unrealized_gain = db.Column(db.Numeric(15, 2), nullable=True)
    last_price_date = db.Column(db.Date, nullable=True)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Extended fields for direct investments, loans, bonds
    org_number = db.Column(db.String(15), nullable=True)
    ownership_pct = db.Column(db.Numeric(7, 4), nullable=True)
    interest_rate = db.Column(db.Numeric(7, 4), nullable=True)
    maturity_date = db.Column(db.Date, nullable=True)
    face_value = db.Column(db.Numeric(15, 2), nullable=True)
    remaining_principal = db.Column(db.Numeric(15, 2), nullable=True)

    company = db.relationship('Company', backref='investment_holdings')
    transactions = db.relationship('InvestmentTransaction', backref='holding')

    @property
    def instrument_type_label(self):
        return INSTRUMENT_TYPE_LABELS.get(self.instrument_type, self.instrument_type)

    @property
    def is_loan_type(self):
        return self.instrument_type in ('lan', 'foretagsobligation')

    def __repr__(self):
        return f'<Holding {self.name} qty={self.quantity}>'


class InvestmentTransaction(db.Model):
    __tablename__ = 'investment_transactions'

    id = db.Column(db.Integer, primary_key=True)
    portfolio_id = db.Column(db.Integer, db.ForeignKey('investment_portfolios.id'), nullable=False)
    holding_id = db.Column(db.Integer, db.ForeignKey('investment_holdings.id'), nullable=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    transaction_date = db.Column(db.Date, nullable=False)
    transaction_type = db.Column(db.String(30), nullable=False)
    quantity = db.Column(db.Numeric(15, 4), nullable=True)
    price_per_unit = db.Column(db.Numeric(15, 4), nullable=True)
    amount = db.Column(db.Numeric(15, 2), nullable=False)
    currency = db.Column(db.String(3), default='SEK')
    exchange_rate = db.Column(db.Numeric(10, 6), default=1.0)
    amount_sek = db.Column(db.Numeric(15, 2), nullable=False)
    commission = db.Column(db.Numeric(15, 2), default=0)
    realized_gain = db.Column(db.Numeric(15, 2), nullable=True)
    verification_id = db.Column(db.Integer, db.ForeignKey('verifications.id'), nullable=True)
    import_batch = db.Column(db.String(50), nullable=True)
    note = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    company = db.relationship('Company', backref='investment_transactions')
    verification = db.relationship('Verification')

    @property
    def transaction_type_label(self):
        return TRANSACTION_TYPE_LABELS.get(self.transaction_type, self.transaction_type)

    def __repr__(self):
        return f'<InvTransaction {self.transaction_type} {self.amount}>'

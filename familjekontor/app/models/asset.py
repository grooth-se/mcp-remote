from datetime import datetime, timezone
from app.extensions import db


# K2 category defaults: (asset_account, depreciation_account, expense_account, useful_life_months)
ASSET_CATEGORY_DEFAULTS = {
    'immateriella': ('1010', '1019', '7810', 60),
    'byggnader_mark': ('1110', '1119', '7820', 600),
    'maskiner': ('1210', '1219', '7831', 60),
    'inventarier': ('1220', '1229', '7832', 60),
    'bilar': ('1240', '1249', '7834', 60),
    'datorer': ('1250', '1259', '7835', 36),
}

ASSET_CATEGORY_LABELS = {
    'immateriella': 'Immateriella tillgångar',
    'byggnader_mark': 'Byggnader och mark',
    'maskiner': 'Maskiner och tekniska anläggningar',
    'inventarier': 'Inventarier, verktyg och installationer',
    'bilar': 'Bilar och transportmedel',
    'datorer': 'Datorer',
}


class FixedAsset(db.Model):
    __tablename__ = 'fixed_assets'

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    asset_number = db.Column(db.String(20), nullable=False)
    description = db.Column(db.String(500), nullable=True)
    asset_category = db.Column(db.String(50), nullable=False)

    # Purchase info
    purchase_date = db.Column(db.Date, nullable=False)
    purchase_amount = db.Column(db.Numeric(15, 2), nullable=False)
    supplier_name = db.Column(db.String(200), nullable=True)
    invoice_reference = db.Column(db.String(100), nullable=True)

    # Depreciation config
    depreciation_method = db.Column(db.String(20), default='straight_line')
    useful_life_months = db.Column(db.Integer, nullable=False)
    residual_value = db.Column(db.Numeric(15, 2), default=0)
    depreciation_start = db.Column(db.Date, nullable=False)

    # BAS accounts
    asset_account = db.Column(db.String(10), nullable=False)
    depreciation_account = db.Column(db.String(10), nullable=False)
    expense_account = db.Column(db.String(10), nullable=False)

    # State
    status = db.Column(db.String(20), default='active')  # active, fully_depreciated, disposed
    disposed_date = db.Column(db.Date, nullable=True)
    disposal_amount = db.Column(db.Numeric(15, 2), nullable=True)
    disposal_verification_id = db.Column(db.Integer, db.ForeignKey('verifications.id'), nullable=True)
    purchase_verification_id = db.Column(db.Integer, db.ForeignKey('verifications.id'), nullable=True)

    # Tracking
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    company = db.relationship('Company', backref='fixed_assets')
    disposal_verification = db.relationship('Verification', foreign_keys=[disposal_verification_id])
    purchase_verification = db.relationship('Verification', foreign_keys=[purchase_verification_id])

    __table_args__ = (
        db.UniqueConstraint('company_id', 'asset_number', name='uq_company_asset_number'),
    )

    @property
    def depreciable_amount(self):
        """Amount subject to depreciation."""
        return float(self.purchase_amount) - float(self.residual_value or 0)

    @property
    def category_label(self):
        return ASSET_CATEGORY_LABELS.get(self.asset_category, self.asset_category)

    def __repr__(self):
        return f'<FixedAsset {self.asset_number} {self.name}>'


class DepreciationRun(db.Model):
    __tablename__ = 'depreciation_runs'

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    fiscal_year_id = db.Column(db.Integer, db.ForeignKey('fiscal_years.id'), nullable=False)
    period_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, posted
    verification_id = db.Column(db.Integer, db.ForeignKey('verifications.id'), nullable=True)
    total_amount = db.Column(db.Numeric(15, 2), default=0)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    company = db.relationship('Company', backref='depreciation_runs')
    fiscal_year = db.relationship('FiscalYear', backref='depreciation_runs')
    verification = db.relationship('Verification', backref='depreciation_run')
    entries = db.relationship('DepreciationEntry', backref='run', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<DepreciationRun {self.period_date} {self.status}>'


class DepreciationEntry(db.Model):
    __tablename__ = 'depreciation_entries'

    id = db.Column(db.Integer, primary_key=True)
    depreciation_run_id = db.Column(db.Integer, db.ForeignKey('depreciation_runs.id'), nullable=False)
    asset_id = db.Column(db.Integer, db.ForeignKey('fixed_assets.id'), nullable=False)
    period_amount = db.Column(db.Numeric(15, 2), nullable=False)
    accumulated_before = db.Column(db.Numeric(15, 2), nullable=False)
    accumulated_after = db.Column(db.Numeric(15, 2), nullable=False)
    book_value_after = db.Column(db.Numeric(15, 2), nullable=False)

    asset = db.relationship('FixedAsset', backref='depreciation_entries')

    def __repr__(self):
        return f'<DepreciationEntry asset={self.asset_id} amount={self.period_amount}>'

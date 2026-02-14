from datetime import datetime, timezone
from decimal import Decimal
from app.extensions import db


class VATReport(db.Model):
    __tablename__ = 'vat_reports'

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    fiscal_year_id = db.Column(db.Integer, db.ForeignKey('fiscal_years.id'), nullable=False)
    period_type = db.Column(db.String(20), nullable=False)  # monthly, quarterly, annual
    period_year = db.Column(db.Integer, nullable=False)
    period_month = db.Column(db.Integer, nullable=True)  # 1-12 for monthly
    period_quarter = db.Column(db.Integer, nullable=True)  # 1-4 for quarterly
    period_start = db.Column(db.Date, nullable=False)
    period_end = db.Column(db.Date, nullable=False)
    output_vat_25 = db.Column(db.Numeric(15, 2), default=0)  # 2610
    output_vat_12 = db.Column(db.Numeric(15, 2), default=0)  # 2620
    output_vat_6 = db.Column(db.Numeric(15, 2), default=0)   # 2630
    input_vat = db.Column(db.Numeric(15, 2), default=0)      # 2640+2641+2645
    vat_to_pay = db.Column(db.Numeric(15, 2), default=0)     # net
    status = db.Column(db.String(20), default='draft')  # draft, final, filed
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    company = db.relationship('Company', backref='vat_reports')
    fiscal_year = db.relationship('FiscalYear')
    creator = db.relationship('User', foreign_keys=[created_by])

    def __repr__(self):
        return f'<VATReport {self.period_year} {self.period_type} ({self.status})>'


class Deadline(db.Model):
    __tablename__ = 'deadlines'

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    deadline_type = db.Column(db.String(30), nullable=False)  # vat, employer_tax, corporate_tax, annual_report, tax_return
    description = db.Column(db.String(300), nullable=False)
    due_date = db.Column(db.Date, nullable=False)
    reminder_date = db.Column(db.Date, nullable=True)
    period_label = db.Column(db.String(50))  # e.g. "Jan 2026", "Q1 2026"
    status = db.Column(db.String(20), default='pending')  # pending, completed, overdue
    completed_at = db.Column(db.DateTime, nullable=True)
    completed_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    auto_generated = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    company = db.relationship('Company', backref='deadlines')
    completer = db.relationship('User', foreign_keys=[completed_by])

    def __repr__(self):
        return f'<Deadline {self.deadline_type} {self.due_date} ({self.status})>'


class TaxPayment(db.Model):
    __tablename__ = 'tax_payments'

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    deadline_id = db.Column(db.Integer, db.ForeignKey('deadlines.id'), nullable=True)
    payment_type = db.Column(db.String(30), nullable=False)  # vat, employer_tax, corporate_tax, preliminary_tax
    amount = db.Column(db.Numeric(15, 2), nullable=False)
    payment_date = db.Column(db.Date, nullable=False)
    reference = db.Column(db.String(100), nullable=True)
    verification_id = db.Column(db.Integer, db.ForeignKey('verifications.id'), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    company = db.relationship('Company', backref='tax_payments')
    deadline = db.relationship('Deadline', backref='payments')
    verification = db.relationship('Verification')
    creator = db.relationship('User', foreign_keys=[created_by])

    def __repr__(self):
        return f'<TaxPayment {self.payment_type} {self.amount} ({self.payment_date})>'


# ---------------------------------------------------------------------------
# Tax Return (Inkomstdeklaration)
# ---------------------------------------------------------------------------

# INK2 field mapping (for reference / SRU export)
INK2_FIELDS = {
    'net_revenue': 'R1',
    'other_operating_income': 'R2',
    'operating_expenses': 'R3',
    'depreciation_booked': 'R4',
    'financial_income': 'R5',
    'financial_expenses': 'R6',
    'net_income': 'R7',
    'taxable_income': 'R16',
}

# Tax rates by company type and year
TAX_RATES = {
    'AB': Decimal('0.206'),   # 20.6% bolagsskatt
    'HB': Decimal('0'),       # HB: pass-through, no entity-level tax
    'EF': Decimal('0'),       # EF: pass-through
}


class TaxReturn(db.Model):
    """Inkomstdeklaration (yearly tax return) for a company."""
    __tablename__ = 'tax_returns'

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    fiscal_year_id = db.Column(db.Integer, db.ForeignKey('fiscal_years.id'), nullable=False)
    return_type = db.Column(db.String(10), nullable=False)  # ink2 / ink4
    tax_year = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default='draft')  # draft / submitted / approved

    # Auto-populated from P&L
    net_revenue = db.Column(db.Numeric(15, 2), default=0)
    other_operating_income = db.Column(db.Numeric(15, 2), default=0)
    operating_expenses = db.Column(db.Numeric(15, 2), default=0)
    depreciation_booked = db.Column(db.Numeric(15, 2), default=0)
    financial_income = db.Column(db.Numeric(15, 2), default=0)
    financial_expenses = db.Column(db.Numeric(15, 2), default=0)
    net_income = db.Column(db.Numeric(15, 2), default=0)  # Årets resultat

    # Tax adjustments (manual)
    non_deductible_expenses = db.Column(db.Numeric(15, 2), default=0)
    non_taxable_income = db.Column(db.Numeric(15, 2), default=0)
    depreciation_tax_diff = db.Column(db.Numeric(15, 2), default=0)
    other_adjustments_add = db.Column(db.Numeric(15, 2), default=0)
    other_adjustments_deduct = db.Column(db.Numeric(15, 2), default=0)

    # Calculated
    taxable_income_before_deficit = db.Column(db.Numeric(15, 2), default=0)
    previous_deficit = db.Column(db.Numeric(15, 2), default=0)
    taxable_income = db.Column(db.Numeric(15, 2), default=0)
    tax_rate = db.Column(db.Numeric(5, 4), default=Decimal('0.206'))
    calculated_tax = db.Column(db.Numeric(15, 2), default=0)

    notes = db.Column(db.Text, nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    submitted_at = db.Column(db.DateTime, nullable=True)

    company = db.relationship('Company', backref='tax_returns')
    fiscal_year = db.relationship('FiscalYear')
    creator = db.relationship('User', foreign_keys=[created_by])
    adjustments = db.relationship('TaxReturnAdjustment', backref='tax_return',
                                  cascade='all, delete-orphan',
                                  order_by='TaxReturnAdjustment.id')

    @property
    def return_type_label(self):
        labels = {'ink2': 'INK2 (Aktiebolag)', 'ink4': 'INK4 (Handelsbolag)'}
        return labels.get(self.return_type, self.return_type)

    @property
    def status_label(self):
        labels = {'draft': 'Utkast', 'submitted': 'Inlämnad', 'approved': 'Godkänd'}
        return labels.get(self.status, self.status)

    def __repr__(self):
        return f'<TaxReturn {self.return_type} {self.tax_year} ({self.status})>'


class TaxReturnAdjustment(db.Model):
    """Individual tax adjustment line items for a tax return."""
    __tablename__ = 'tax_return_adjustments'

    id = db.Column(db.Integer, primary_key=True)
    tax_return_id = db.Column(db.Integer, db.ForeignKey('tax_returns.id'), nullable=False)
    adjustment_type = db.Column(db.String(20), nullable=False)  # add / deduct
    description = db.Column(db.String(500), nullable=False)
    amount = db.Column(db.Numeric(15, 2), nullable=False)
    sru_code = db.Column(db.String(10), nullable=True)  # Optional SRU field reference
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f'<TaxReturnAdjustment {self.adjustment_type} {self.amount}>'

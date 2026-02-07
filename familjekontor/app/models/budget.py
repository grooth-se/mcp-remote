from datetime import datetime, timezone
from app.extensions import db


class BudgetLine(db.Model):
    __tablename__ = 'budget_lines'

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    fiscal_year_id = db.Column(db.Integer, db.ForeignKey('fiscal_years.id'), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=False)
    period_month = db.Column(db.Integer, nullable=False)  # 1-12
    amount = db.Column(db.Numeric(15, 2), default=0)
    notes = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    company = db.relationship('Company', backref='budget_lines')
    fiscal_year = db.relationship('FiscalYear', backref='budget_lines')
    account = db.relationship('Account', backref='budget_lines')

    __table_args__ = (
        db.UniqueConstraint('company_id', 'fiscal_year_id', 'account_id', 'period_month',
                            name='uq_budget_line'),
    )

    def __repr__(self):
        return f'<BudgetLine {self.account_id} M{self.period_month} {self.amount}>'

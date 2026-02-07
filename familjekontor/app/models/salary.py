from datetime import datetime, timezone
from app.extensions import db

MONTH_NAMES_SV = [
    '', 'januari', 'februari', 'mars', 'april', 'maj', 'juni',
    'juli', 'augusti', 'september', 'oktober', 'november', 'december',
]


class Employee(db.Model):
    __tablename__ = 'employees'

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    personal_number = db.Column(db.String(20), nullable=False)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(200), nullable=True)
    employment_start = db.Column(db.Date, nullable=False)
    employment_end = db.Column(db.Date, nullable=True)
    monthly_salary = db.Column(db.Numeric(15, 2), nullable=False)
    tax_table = db.Column(db.String(10), nullable=False, default='33')
    tax_column = db.Column(db.Integer, nullable=False, default=1)
    pension_plan = db.Column(db.String(10), nullable=False, default='ITP1')
    bank_clearing = db.Column(db.String(10), nullable=True)
    bank_account = db.Column(db.String(20), nullable=True)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    company = db.relationship('Company', backref='employees')
    salary_entries = db.relationship('SalaryEntry', backref='employee', lazy='dynamic')

    @property
    def full_name(self):
        return f'{self.first_name} {self.last_name}'

    @property
    def masked_personal_number(self):
        if self.personal_number and len(self.personal_number) >= 4:
            return '******-' + self.personal_number[-4:]
        return '******-****'

    def __repr__(self):
        return f'<Employee {self.full_name} ({self.company_id})>'


class SalaryRun(db.Model):
    __tablename__ = 'salary_runs'

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    fiscal_year_id = db.Column(db.Integer, db.ForeignKey('fiscal_years.id'), nullable=False)
    period_year = db.Column(db.Integer, nullable=False)
    period_month = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default='draft')  # draft, approved, paid
    total_gross = db.Column(db.Numeric(15, 2), default=0)
    total_tax = db.Column(db.Numeric(15, 2), default=0)
    total_net = db.Column(db.Numeric(15, 2), default=0)
    total_employer_contributions = db.Column(db.Numeric(15, 2), default=0)
    total_pension = db.Column(db.Numeric(15, 2), default=0)
    verification_id = db.Column(db.Integer, db.ForeignKey('verifications.id'), nullable=True)
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)
    paid_date = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    company = db.relationship('Company', backref='salary_runs')
    fiscal_year = db.relationship('FiscalYear', backref='salary_runs')
    verification = db.relationship('Verification', backref='salary_run')
    approver = db.relationship('User', foreign_keys=[approved_by])
    entries = db.relationship('SalaryEntry', backref='salary_run', lazy='select',
                              cascade='all, delete-orphan')

    __table_args__ = (
        db.UniqueConstraint('company_id', 'period_year', 'period_month',
                            name='uq_company_salary_period'),
    )

    @property
    def period_label(self):
        return f'{MONTH_NAMES_SV[self.period_month]} {self.period_year}'

    def __repr__(self):
        return f'<SalaryRun {self.period_label} ({self.status})>'


class SalaryEntry(db.Model):
    __tablename__ = 'salary_entries'

    id = db.Column(db.Integer, primary_key=True)
    salary_run_id = db.Column(db.Integer, db.ForeignKey('salary_runs.id'), nullable=False)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    gross_salary = db.Column(db.Numeric(15, 2), default=0)
    tax_deduction = db.Column(db.Numeric(15, 2), default=0)
    net_salary = db.Column(db.Numeric(15, 2), default=0)
    employer_contributions = db.Column(db.Numeric(15, 2), default=0)
    pension_amount = db.Column(db.Numeric(15, 2), default=0)
    vacation_pay_provision = db.Column(db.Numeric(15, 2), default=0)
    other_deductions = db.Column(db.Numeric(15, 2), default=0)
    other_additions = db.Column(db.Numeric(15, 2), default=0)
    notes = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return f'<SalaryEntry {self.employee.full_name if self.employee else "?"} {self.gross_salary}>'

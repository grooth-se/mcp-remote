"""Project monthly fact table and upload session models."""

from datetime import datetime
from app.extensions import db


class FactProjectMonthly(db.Model):
    """Monthly project snapshot for accrued income calculations.

    Composite primary key: (closing_date, project_number)
    """
    __tablename__ = 'fact_project_monthly'

    # Primary Key (composite)
    closing_date = db.Column(db.String(10), primary_key=True)  # 'YYYY-MM-DD'
    project_number = db.Column(db.String(20), primary_key=True)

    # Project Identity
    project_name = db.Column(db.String(200))
    customer_name = db.Column(db.String(200))

    # From Monitor G5 Projektuppfoljning (original values)
    expected_income = db.Column(db.Float, default=0)      # Forvan. intakt
    expected_cost = db.Column(db.Float, default=0)        # Forvan. kostnad
    executed_income = db.Column(db.Float, default=0)      # Utf., intakt
    executed_cost = db.Column(db.Float, default=0)        # Utf., kostnad

    # Actual from Verifikationslista (GL transactions)
    actual_income = db.Column(db.Float, default=0)        # Account 3000-3999
    actual_cost = db.Column(db.Float, default=0)          # Account 4000-6999

    # Time tracking
    cm_cost = db.Column(db.Float, default=0)              # Hours * 475 SEK

    # Purchase order revaluation
    remaining_cost = db.Column(db.Float, default=0)       # Inkopsorder revaluated

    # Customer order revaluation
    remaining_income = db.Column(db.Float, default=0)     # Kundorder revaluated
    remaining_income_val = db.Column(db.Float, default=0) # Original currency amount
    remaining_income_cur = db.Column(db.Float, default=0) # SEK after milestone adj

    # Milestone data
    milestone_amount = db.Column(db.Float, default=0)     # Milestone in SEK
    milestone_cur = db.Column(db.Float, default=0)        # Milestone in orig currency

    # Original calculation metrics
    profit_margin = db.Column(db.Float, default=0)        # vinstmarg
    cost_factor = db.Column(db.Float, default=0)          # kostfakt
    completion_rate = db.Column(db.Float, default=0)      # fardiggrad (0-1)
    accrued_income = db.Column(db.Float, default=0)       # Original accrued income
    risk_amount = db.Column(db.Float, default=0)          # risk

    # Currency-adjusted totals
    actual_income_cur = db.Column(db.Float, default=0)    # actincome CUR
    actual_cost_cur = db.Column(db.Float, default=0)      # actcost CUR
    total_income_cur = db.Column(db.Float, default=0)     # totalincome CUR
    total_cost_cur = db.Column(db.Float, default=0)       # totalcost CUR

    # Currency-adjusted metrics
    profit_margin_cur = db.Column(db.Float, default=0)    # profit margin CUR
    actual_cost_invoiced_cur = db.Column(db.Float, default=0)  # actcost invo CUR
    completion_cur = db.Column(db.Float, default=0)       # completion CUR
    completion_cur1 = db.Column(db.Float, default=0)      # completion CUR1

    # Final accrued income and contingency
    accrued_income_cur = db.Column(db.Float, default=0)   # accured income CUR
    contingency_cur = db.Column(db.Float, default=0)      # contingency CUR

    # Adjustments from projectadjustments.xlsx
    include_in_accrued = db.Column(db.Boolean, default=True)  # incl
    contingency_factor = db.Column(db.Float, default=0)   # complex
    income_adjustment = db.Column(db.Float, default=0)    # incomeadj
    cost_calc_adjustment = db.Column(db.Float, default=0) # costcalcadj
    purchase_adjustment = db.Column(db.Float, default=0)  # puradj

    # Variance analysis
    project_profit = db.Column(db.Float, default=0)       # projloss
    diff_income = db.Column(db.Float, default=0)          # diffincome
    diff_cost = db.Column(db.Float, default=0)            # diffcost

    # Metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Project {self.project_number} @ {self.closing_date}>'

    @classmethod
    def get_closing_dates(cls):
        """Return all distinct closing dates, sorted descending."""
        results = db.session.query(cls.closing_date).distinct()\
            .order_by(cls.closing_date.desc()).all()
        return [r[0] for r in results]

    @classmethod
    def get_by_closing_date(cls, closing_date):
        """Return all projects for a given closing date."""
        return cls.query.filter_by(closing_date=closing_date)\
            .order_by(cls.project_number).all()


class UploadSession(db.Model):
    """Track file upload sessions."""
    __tablename__ = 'upload_session'

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(36), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    closing_date = db.Column(db.String(10))
    status = db.Column(db.String(20), default='pending')
    files_json = db.Column(db.Text)  # JSON dict of file paths
    validation_errors = db.Column(db.Text)  # JSON array of errors
    result_count = db.Column(db.Integer, default=0)

    def __repr__(self):
        return f'<UploadSession {self.session_id} [{self.status}]>'

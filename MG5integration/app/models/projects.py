from app.extensions import db
from app.models.base import TimestampMixin


class Project(TimestampMixin, db.Model):
    """Project follow-up from projektuppf.xlsx.

    Source columns: Projektnummer, Benämning, Kundnamn,
    Startdatum, Slutdatum, Utf. kostnad, Utf. intäkt,
    Förvän. kostnad, Förvän. intäkt, Rest. kostnad, Rest. intäkt
    """
    __tablename__ = 'projects'

    id = db.Column(db.Integer, primary_key=True)
    project_number = db.Column(db.String(20), unique=True, nullable=False, index=True)
    description = db.Column(db.String(300))  # Benämning
    customer = db.Column(db.String(200))  # Kundnamn
    start_date = db.Column(db.Date)  # Startdatum
    end_date = db.Column(db.Date)  # Slutdatum
    executed_cost = db.Column(db.Float, default=0)  # Utf., kostnad
    executed_income = db.Column(db.Float, default=0)  # Utf., intäkt
    expected_cost = db.Column(db.Float, default=0)  # Förvän. kostnad
    expected_income = db.Column(db.Float, default=0)  # Förvän. intäkt
    remaining_cost = db.Column(db.Float, default=0)  # Rest. kostnad
    remaining_income = db.Column(db.Float, default=0)  # Rest. intäkt

    adjustments = db.relationship('ProjectAdjustment', backref='project', lazy='dynamic')
    time_entries = db.relationship('TimeTracking', backref='project', lazy='dynamic')

    def to_dict(self):
        return {
            'id': self.id,
            'project_number': self.project_number,
            'description': self.description,
            'customer': self.customer,
            'start_date': self.start_date.isoformat() if self.start_date else None,
            'end_date': self.end_date.isoformat() if self.end_date else None,
            'executed_cost': self.executed_cost,
            'executed_income': self.executed_income,
            'expected_cost': self.expected_cost,
            'expected_income': self.expected_income,
            'remaining_cost': self.remaining_cost,
            'remaining_income': self.remaining_income,
        }


class ProjectAdjustment(TimestampMixin, db.Model):
    """Project adjustments from projectadjustments.xlsx.

    Source columns: Projektnummer, Benämning, Kundnamn,
    Accured, Contingency, Incomeadj, Costcalcadj, puradj, Closing
    """
    __tablename__ = 'project_adjustments'

    id = db.Column(db.Integer, primary_key=True)
    project_number = db.Column(
        db.String(20),
        db.ForeignKey('projects.project_number'),
        index=True
    )
    description = db.Column(db.String(300))  # Benämning
    customer = db.Column(db.String(200))  # Kundnamn
    include_in_accrued = db.Column(db.Boolean, default=True)  # Accured
    contingency = db.Column(db.Float, default=0)  # Contingency
    income_adjustment = db.Column(db.Float, default=0)  # Incomeadj
    cost_calc_adjustment = db.Column(db.Float, default=0)  # Costcalcadj
    purchase_adjustment = db.Column(db.Float, default=0)  # puradj
    closing_date = db.Column(db.String(20))  # Closing

    def to_dict(self):
        return {
            'id': self.id,
            'project_number': self.project_number,
            'description': self.description,
            'customer': self.customer,
            'include_in_accrued': self.include_in_accrued,
            'contingency': self.contingency,
            'income_adjustment': self.income_adjustment,
            'cost_calc_adjustment': self.cost_calc_adjustment,
            'purchase_adjustment': self.purchase_adjustment,
            'closing_date': self.closing_date,
        }


class TimeTracking(TimestampMixin, db.Model):
    """Time tracking from tiduppfoljning.xlsx.

    Source columns: Projektnummer, Benämning, Budget,
    Planerad tid, Utfall, Förväntat, Prognos, Rest.
    """
    __tablename__ = 'time_tracking'

    id = db.Column(db.Integer, primary_key=True)
    project_number = db.Column(
        db.String(20),
        db.ForeignKey('projects.project_number'),
        index=True
    )
    description = db.Column(db.String(300))  # Benämning
    budget = db.Column(db.Float)  # Budget
    planned_time = db.Column(db.Float, default=0)  # Planerad tid
    actual_hours = db.Column(db.Float, default=0)  # Utfall
    expected_hours = db.Column(db.Float, default=0)  # Förväntat
    forecast = db.Column(db.Float)  # Prognos
    remaining = db.Column(db.Float, default=0)  # Rest.

    def to_dict(self):
        return {
            'id': self.id,
            'project_number': self.project_number,
            'description': self.description,
            'budget': self.budget,
            'planned_time': self.planned_time,
            'actual_hours': self.actual_hours,
            'expected_hours': self.expected_hours,
            'forecast': self.forecast,
            'remaining': self.remaining,
        }


class CustomerOrderProjectMap(TimestampMixin, db.Model):
    """Customer order to project mapping from CO_proj_crossref.xlsx.

    Source columns: Ordernummer, Projekt
    """
    __tablename__ = 'co_project_crossref'

    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.Integer, index=True)  # Ordernummer
    project_number = db.Column(db.String(20), index=True)  # Projekt

    def to_dict(self):
        return {
            'id': self.id,
            'order_number': self.order_number,
            'project_number': self.project_number,
        }

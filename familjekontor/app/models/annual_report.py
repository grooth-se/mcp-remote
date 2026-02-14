from datetime import datetime, timezone
from app.extensions import db


class AnnualReport(db.Model):
    __tablename__ = 'annual_reports'

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    fiscal_year_id = db.Column(db.Integer, db.ForeignKey('fiscal_years.id'), nullable=False)
    status = db.Column(db.String(20), default='draft')  # draft, final

    # Förvaltningsberättelse
    verksamhet = db.Column(db.Text, nullable=True)
    vasentliga_handelser = db.Column(db.Text, nullable=True)
    handelser_efter_fy = db.Column(db.Text, nullable=True)
    framtida_utveckling = db.Column(db.Text, nullable=True)
    resultatdisposition = db.Column(db.Text, nullable=True)

    # Noter
    redovisningsprinciper = db.Column(db.Text, nullable=True)
    extra_noter = db.Column(db.Text, nullable=True)

    # Underskrifter
    board_members = db.Column(db.Text, nullable=True)
    signing_location = db.Column(db.String(200), nullable=True)
    signing_date = db.Column(db.Date, nullable=True)

    # PDF
    pdf_path = db.Column(db.String(500), nullable=True)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    company = db.relationship('Company', backref='annual_reports')
    fiscal_year = db.relationship('FiscalYear', backref='annual_reports')
    creator = db.relationship('User', foreign_keys=[created_by])

    __table_args__ = (
        db.UniqueConstraint('company_id', 'fiscal_year_id',
                            name='uq_company_fy_annual_report'),
    )

    def __repr__(self):
        return f'<AnnualReport {self.company_id} FY:{self.fiscal_year_id} ({self.status})>'

"""SavedReport model for storing user-defined report configurations."""

from datetime import datetime, timezone

from app.extensions import db


class SavedReport(db.Model):
    __tablename__ = 'saved_reports'

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    report_type = db.Column(db.String(50), nullable=False)  # pnl, balance, cashflow, ratios, comparison, arap
    parameters = db.Column(db.Text)  # JSON-encoded parameters
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    company = db.relationship('Company', backref='saved_reports')
    user = db.relationship('User', backref='saved_reports')

    def __repr__(self):
        return f'<SavedReport {self.name} ({self.report_type})>'

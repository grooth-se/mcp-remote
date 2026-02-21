"""Cost center model for tracking expenses/revenue by department or project."""

from datetime import datetime, timezone
from app.extensions import db


class CostCenter(db.Model):
    __tablename__ = 'cost_centers'
    __table_args__ = (
        db.UniqueConstraint('company_id', 'code', name='uq_cost_center_company_code'),
    )

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    code = db.Column(db.String(20), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    company = db.relationship('Company', backref='cost_centers')

    def __repr__(self):
        return f'<CostCenter {self.code} {self.name}>'

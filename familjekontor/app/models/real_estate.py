"""Real estate model for property tracking beyond generic fixed assets."""

from datetime import datetime, timezone
from app.extensions import db


class RealEstate(db.Model):
    __tablename__ = 'real_estates'

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    asset_id = db.Column(db.Integer, db.ForeignKey('fixed_assets.id'), nullable=True)
    property_name = db.Column(db.String(200), nullable=False)
    fastighetsbeteckning = db.Column(db.String(100))
    street_address = db.Column(db.String(200))
    postal_code = db.Column(db.String(10))
    city = db.Column(db.String(100))
    taxeringsvarde = db.Column(db.Numeric(15, 2), default=0)
    taxeringsvarde_year = db.Column(db.Integer)
    property_tax_rate = db.Column(db.Numeric(6, 4), default=0.0075)
    monthly_rent_target = db.Column(db.Numeric(15, 2), default=0)
    rent_account = db.Column(db.String(10), default='3910')
    notes = db.Column(db.Text)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    company = db.relationship('Company', backref='real_estates')
    asset = db.relationship('FixedAsset', backref=db.backref('real_estate', uselist=False))

    def __repr__(self):
        return f'<RealEstate {self.property_name}>'

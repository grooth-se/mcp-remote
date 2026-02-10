from datetime import datetime, timezone
from app.extensions import db


class ExchangeRate(db.Model):
    __tablename__ = 'exchange_rates'

    id = db.Column(db.Integer, primary_key=True)
    currency_code = db.Column(db.String(3), nullable=False)
    rate_date = db.Column(db.Date, nullable=False)
    rate = db.Column(db.Numeric(12, 6), nullable=False)  # 1 foreign = X SEK
    inverse_rate = db.Column(db.Numeric(12, 6), nullable=True)  # Riksbanken raw: 1 SEK = X foreign
    source = db.Column(db.String(20), default='manual')  # riksbanken / manual
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.UniqueConstraint('currency_code', 'rate_date', name='uq_currency_rate_date'),
    )

    def __repr__(self):
        return f'<ExchangeRate {self.currency_code} {self.rate_date} {self.rate}>'

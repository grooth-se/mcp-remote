from app.extensions import db
from app.models.base import TimestampMixin


class InvoiceLog(TimestampMixin, db.Model):
    """Invoice log from faktureringslogg.xlsx.

    Source columns: Fakturanummer, Fakt.datum, Projekt, Ordernummer,
    Kundnamn faktura, Artikel – Artikelnummer, Artikelnummer,
    À-pris, À-pris val., Belopp, Belopp val., Valutakurs, Terminskurs
    """
    __tablename__ = 'invoice_log'

    id = db.Column(db.Integer, primary_key=True)
    invoice_number = db.Column(db.Integer, index=True)  # Fakturanummer
    date = db.Column(db.Date, index=True)  # Fakt.datum
    project = db.Column(db.String(20), index=True)  # Projekt
    order_number = db.Column(db.Integer)  # Ordernummer
    customer_name = db.Column(db.String(200))  # Kundnamn faktura
    article_category = db.Column(db.String(50))  # Artikel – Artikelnummer
    article_number = db.Column(db.String(50))  # Artikelnummer
    unit_price = db.Column(db.Float, default=0)  # À-pris (SEK)
    unit_price_currency = db.Column(db.Float, default=0)  # À-pris val.
    amount = db.Column(db.Float, default=0)  # Belopp (SEK)
    amount_currency = db.Column(db.Float, default=0)  # Belopp val.
    exchange_rate = db.Column(db.Float, default=1.0)  # Valutakurs
    forward_rate = db.Column(db.Boolean, default=False)  # Terminskurs

    def to_dict(self):
        return {
            'id': self.id,
            'invoice_number': self.invoice_number,
            'date': self.date.isoformat() if self.date else None,
            'project': self.project,
            'order_number': self.order_number,
            'customer_name': self.customer_name,
            'article_category': self.article_category,
            'article_number': self.article_number,
            'unit_price': self.unit_price,
            'unit_price_currency': self.unit_price_currency,
            'amount': self.amount,
            'amount_currency': self.amount_currency,
            'exchange_rate': self.exchange_rate,
            'forward_rate': self.forward_rate,
        }


class ExchangeRate(TimestampMixin, db.Model):
    """Exchange rates from valutakurser.xlsx.

    Source columns: DATE, DKK, EUR, GBP, NOK, SEK, USD
    """
    __tablename__ = 'exchange_rates'

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, unique=True, index=True)  # DATE
    dkk = db.Column(db.Float)
    eur = db.Column(db.Float)
    gbp = db.Column(db.Float)
    nok = db.Column(db.Float)
    sek = db.Column(db.Float, default=1.0)
    usd = db.Column(db.Float)

    def to_dict(self):
        return {
            'id': self.id,
            'date': self.date.isoformat() if self.date else None,
            'dkk': self.dkk,
            'eur': self.eur,
            'gbp': self.gbp,
            'nok': self.nok,
            'sek': self.sek,
            'usd': self.usd,
        }

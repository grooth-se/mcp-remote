from app.extensions import db
from app.models.base import TimestampMixin


class Article(TimestampMixin, db.Model):
    """Articles from Artikellista-*.xlsx.

    Source columns: Artikelnummer, Artikelbenämning, Artikelns PIA-saldo,
    Lagerplats, Serienummer, Batchnummer,
    Klarerat saldo (inkl. utgånget), Tillgängligt saldo, Totalt saldo
    """
    __tablename__ = 'articles'

    id = db.Column(db.Integer, primary_key=True)
    article_number = db.Column(db.String(50), unique=True, index=True)  # Artikelnummer
    description = db.Column(db.String(300))  # Artikelbenämning
    wip_balance = db.Column(db.Float, default=0)  # Artikelns PIA-saldo
    location = db.Column(db.String(50))  # Lagerplats
    serial_number = db.Column(db.String(50))  # Serienummer
    batch_number = db.Column(db.String(50))  # Batchnummer
    cleared_balance = db.Column(db.Float, default=0)  # Klarerat saldo (inkl. utgånget)
    available_balance = db.Column(db.Float, default=0)  # Tillgängligt saldo
    total_balance = db.Column(db.Float, default=0)  # Totalt saldo

    def to_dict(self):
        return {
            'id': self.id,
            'article_number': self.article_number,
            'description': self.description,
            'wip_balance': self.wip_balance,
            'location': self.location,
            'serial_number': self.serial_number,
            'batch_number': self.batch_number,
            'cleared_balance': self.cleared_balance,
            'available_balance': self.available_balance,
            'total_balance': self.total_balance,
        }


class MinimumStock(TimestampMixin, db.Model):
    """Minimum stock levels from Min stock per artikel.xlsx.

    Source columns: Lagertyp, Artikelnummer, OD, GRADE, Beställt antal
    """
    __tablename__ = 'minimum_stock'

    id = db.Column(db.Integer, primary_key=True)
    stock_type = db.Column(db.String(30))  # Lagertyp
    article_number = db.Column(db.String(50), index=True)  # Artikelnummer
    outer_diameter = db.Column(db.Float)  # OD
    grade = db.Column(db.String(20))  # GRADE
    ordered_quantity = db.Column(db.Float, default=0)  # Beställt antal

    def to_dict(self):
        return {
            'id': self.id,
            'stock_type': self.stock_type,
            'article_number': self.article_number,
            'outer_diameter': self.outer_diameter,
            'grade': self.grade,
            'ordered_quantity': self.ordered_quantity,
        }

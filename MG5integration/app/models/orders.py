from app.extensions import db
from app.models.base import TimestampMixin


class CustomerOrder(TimestampMixin, db.Model):
    """Customer orders from kundorderforteckning.xlsx.

    Source columns: Ordernummer, Projekt, Projektbenämning, Kundnummer,
    Kundnamn, Kundens ordernummer, Orderdatum, Artikelnummer, Benämning,
    Restbelopp, Restbelopp val., Betalningsvillkor, Valuta, Valutakurs,
    À-pris, À-pris val.
    """
    __tablename__ = 'customer_orders'

    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.Integer, index=True)  # Ordernummer
    project = db.Column(db.String(20), index=True)  # Projekt
    project_description = db.Column(db.String(300))  # Projektbenämning
    customer_number = db.Column(db.Integer)  # Kundnummer
    customer_name = db.Column(db.String(200))  # Kundnamn
    customer_order_number = db.Column(db.String(50))  # Kundens ordernummer
    order_date = db.Column(db.Date)  # Orderdatum
    article_number = db.Column(db.String(50))  # Artikelnummer
    article_description = db.Column(db.String(300))  # Benämning
    remaining_amount = db.Column(db.Float, default=0)  # Restbelopp
    remaining_amount_currency = db.Column(db.Float, default=0)  # Restbelopp val.
    payment_terms = db.Column(db.Integer)  # Betalningsvillkor (days)
    currency = db.Column(db.String(3))  # Valuta
    exchange_rate = db.Column(db.Float, default=1.0)  # Valutakurs
    unit_price = db.Column(db.Float, default=0)  # À-pris
    unit_price_currency = db.Column(db.Float, default=0)  # À-pris val.

    def to_dict(self):
        return {
            'id': self.id,
            'order_number': self.order_number,
            'project': self.project,
            'project_description': self.project_description,
            'customer_number': self.customer_number,
            'customer_name': self.customer_name,
            'customer_order_number': self.customer_order_number,
            'order_date': self.order_date.isoformat() if self.order_date else None,
            'article_number': self.article_number,
            'article_description': self.article_description,
            'remaining_amount': self.remaining_amount,
            'remaining_amount_currency': self.remaining_amount_currency,
            'payment_terms': self.payment_terms,
            'currency': self.currency,
            'exchange_rate': self.exchange_rate,
            'unit_price': self.unit_price,
            'unit_price_currency': self.unit_price_currency,
        }


class PurchaseOrder(TimestampMixin, db.Model):
    """Purchase orders from inkoporderforteckning.xlsx.

    Source columns: Tillv order, Projekt, Tillverkningsorder, Ordernummer,
    Pos., Artikelnummer, Benämning, Leveransdatum, À-pris, À-pris val.,
    Beställt antal, Inlevererat antal, Resterande antal, Bekräftad – Rad,
    Restbelopp, Belopp val., Konto, Inköpsorder, Projektbenämning,
    Leverantörsnamn, Lev. ordernr, Orderdatum, Kundorder,
    Postadress – Land, Valuta, Önskat leveransdatum, Godsmärke
    """
    __tablename__ = 'purchase_orders'

    id = db.Column(db.Integer, primary_key=True)
    manufacturing_order_ref = db.Column(db.String(20))  # Tillv order
    project = db.Column(db.String(20), index=True)  # Projekt
    manufacturing_order = db.Column(db.Integer)  # Tillverkningsorder
    order_number = db.Column(db.Integer, index=True)  # Ordernummer
    position = db.Column(db.Integer)  # Pos.
    article_number = db.Column(db.String(50))  # Artikelnummer
    article_description = db.Column(db.String(300))  # Benämning
    delivery_date = db.Column(db.Date)  # Leveransdatum
    unit_price = db.Column(db.Float, default=0)  # À-pris (SEK)
    unit_price_currency = db.Column(db.Float, default=0)  # À-pris val.
    quantity_ordered = db.Column(db.Float, default=0)  # Beställt antal
    quantity_received = db.Column(db.Float, default=0)  # Inlevererat antal
    quantity_remaining = db.Column(db.Float, default=0)  # Resterande antal
    confirmed = db.Column(db.Boolean, default=False)  # Bekräftad – Rad
    remaining_amount = db.Column(db.Float, default=0)  # Restbelopp
    amount_currency = db.Column(db.Float, default=0)  # Belopp val.
    account = db.Column(db.Integer)  # Konto
    is_purchase_order = db.Column(db.Boolean, default=False)  # Inköpsorder
    project_description = db.Column(db.String(300))  # Projektbenämning
    supplier_name = db.Column(db.String(200))  # Leverantörsnamn
    supplier_order_number = db.Column(db.String(50))  # Lev. ordernr
    order_date = db.Column(db.Date)  # Orderdatum
    customer_order = db.Column(db.String(50))  # Kundorder
    country = db.Column(db.String(10))  # Postadress – Land
    currency = db.Column(db.String(3))  # Valuta
    requested_delivery_date = db.Column(db.Date)  # Önskat leveransdatum
    goods_marking = db.Column(db.String(50))  # Godsmärke

    def to_dict(self):
        return {
            'id': self.id,
            'manufacturing_order_ref': self.manufacturing_order_ref,
            'project': self.project,
            'manufacturing_order': self.manufacturing_order,
            'order_number': self.order_number,
            'position': self.position,
            'article_number': self.article_number,
            'article_description': self.article_description,
            'delivery_date': self.delivery_date.isoformat() if self.delivery_date else None,
            'unit_price': self.unit_price,
            'unit_price_currency': self.unit_price_currency,
            'quantity_ordered': self.quantity_ordered,
            'quantity_received': self.quantity_received,
            'quantity_remaining': self.quantity_remaining,
            'confirmed': self.confirmed,
            'remaining_amount': self.remaining_amount,
            'amount_currency': self.amount_currency,
            'account': self.account,
            'is_purchase_order': self.is_purchase_order,
            'project_description': self.project_description,
            'supplier_name': self.supplier_name,
            'supplier_order_number': self.supplier_order_number,
            'order_date': self.order_date.isoformat() if self.order_date else None,
            'customer_order': self.customer_order,
            'country': self.country,
            'currency': self.currency,
            'requested_delivery_date': (
                self.requested_delivery_date.isoformat()
                if self.requested_delivery_date else None
            ),
            'goods_marking': self.goods_marking,
        }


class Quote(TimestampMixin, db.Model):
    """Quotes from Offertförteckning-*.xlsx.

    Source columns: Offertnummer, Lagerställe, Ordertyp, Kund, Namn,
    Status, Förfrågannr, Giltighet, Kundens referens, Telefonnummer,
    Pos., Artikelnummer, Benämning, Leveransdatum, Antal, À-pris,
    Rabatt, Ställpris, Belopp
    """
    __tablename__ = 'quotes'

    id = db.Column(db.Integer, primary_key=True)
    quote_number = db.Column(db.String(30), index=True)  # Offertnummer
    warehouse = db.Column(db.String(10))  # Lagerställe
    order_type = db.Column(db.String(20))  # Ordertyp
    customer_number = db.Column(db.Integer)  # Kund
    customer_name = db.Column(db.String(200))  # Namn
    status = db.Column(db.String(30))  # Status
    inquiry_number = db.Column(db.String(30))  # Förfrågannr
    validity_date = db.Column(db.Date)  # Giltighet
    customer_reference = db.Column(db.String(100))  # Kundens referens
    phone = db.Column(db.String(30))  # Telefonnummer
    position = db.Column(db.Integer)  # Pos.
    article_number = db.Column(db.String(50))  # Artikelnummer
    article_description = db.Column(db.String(300))  # Benämning
    delivery_date = db.Column(db.Date)  # Leveransdatum
    quantity = db.Column(db.Float, default=0)  # Antal
    unit_price = db.Column(db.Float, default=0)  # À-pris
    discount = db.Column(db.Float, default=0)  # Rabatt
    setup_price = db.Column(db.Float, default=0)  # Ställpris
    amount = db.Column(db.Float, default=0)  # Belopp

    def to_dict(self):
        return {
            'id': self.id,
            'quote_number': self.quote_number,
            'warehouse': self.warehouse,
            'order_type': self.order_type,
            'customer_number': self.customer_number,
            'customer_name': self.customer_name,
            'status': self.status,
            'inquiry_number': self.inquiry_number,
            'validity_date': self.validity_date.isoformat() if self.validity_date else None,
            'customer_reference': self.customer_reference,
            'phone': self.phone,
            'position': self.position,
            'article_number': self.article_number,
            'article_description': self.article_description,
            'delivery_date': self.delivery_date.isoformat() if self.delivery_date else None,
            'quantity': self.quantity,
            'unit_price': self.unit_price,
            'discount': self.discount,
            'setup_price': self.setup_price,
            'amount': self.amount,
        }


class OrderIntake(TimestampMixin, db.Model):
    """Order intake from Orderingång-*.xlsx.

    Source columns: Loggdatum, Ordernummer, Kund, Kundnamn,
    Ordertyp, Säljare, Pos., Artikelnummer, Benämning,
    Antal, Pris, Värde
    """
    __tablename__ = 'order_intake'

    id = db.Column(db.Integer, primary_key=True)
    log_date = db.Column(db.DateTime, index=True)  # Loggdatum
    order_number = db.Column(db.Integer, index=True)  # Ordernummer
    customer_number = db.Column(db.Integer)  # Kund
    customer_name = db.Column(db.String(200))  # Kundnamn
    order_type = db.Column(db.String(30))  # Ordertyp
    salesperson = db.Column(db.String(100))  # Säljare
    position = db.Column(db.Integer)  # Pos.
    article_number = db.Column(db.String(50))  # Artikelnummer
    article_description = db.Column(db.String(300))  # Benämning
    quantity = db.Column(db.Float, default=0)  # Antal
    price = db.Column(db.Float, default=0)  # Pris
    value = db.Column(db.Float, default=0)  # Värde

    def to_dict(self):
        return {
            'id': self.id,
            'log_date': self.log_date.isoformat() if self.log_date else None,
            'order_number': self.order_number,
            'customer_number': self.customer_number,
            'customer_name': self.customer_name,
            'order_type': self.order_type,
            'salesperson': self.salesperson,
            'position': self.position,
            'article_number': self.article_number,
            'article_description': self.article_description,
            'quantity': self.quantity,
            'price': self.price,
            'value': self.value,
        }

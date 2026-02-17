from app.extensions import db
from app.models.base import TimestampMixin


class Account(TimestampMixin, db.Model):
    """Chart of accounts from kontoplan.xlsx.

    Source columns: Konto, Benämning, Kontotyp, SRU-kod, D/K
    """
    __tablename__ = 'accounts'

    id = db.Column(db.Integer, primary_key=True)
    account_number = db.Column(db.Integer, unique=True, nullable=False, index=True)
    description = db.Column(db.String(200))
    account_type = db.Column(db.String(50))  # Tillgångar, Skulder, Intäkter, Kostnader
    sru_code = db.Column(db.String(20))
    debit_credit = db.Column(db.String(10))  # Debet / Kredit

    def to_dict(self):
        return {
            'id': self.id,
            'account_number': self.account_number,
            'description': self.description,
            'account_type': self.account_type,
            'sru_code': self.sru_code,
            'debit_credit': self.debit_credit,
        }


class Verification(TimestampMixin, db.Model):
    """Journal entries from verlista.xlsx.

    Source columns: Ver.nr, Ver.datum, Verifikationstext,
    Rättning till/Kopia av, Rättad av/Kopia av, Preliminär,
    Konto, Benämning, Kst, Kb, Proj., Specifikation, Debet, Kredit
    """
    __tablename__ = 'verifications'

    id = db.Column(db.Integer, primary_key=True)
    verification_number = db.Column(db.String(20), index=True)  # Ver.nr e.g. "1-1"
    date = db.Column(db.Date, index=True)  # Ver.datum
    text = db.Column(db.String(500))  # Verifikationstext
    correction_ref = db.Column(db.String(50))  # Rättning till/Kopia av
    corrected_by = db.Column(db.String(50))  # Rättad av/Kopia av
    preliminary = db.Column(db.Boolean, default=False)  # Preliminär
    account = db.Column(db.Integer, index=True)  # Konto
    account_description = db.Column(db.String(200))  # Benämning
    cost_center = db.Column(db.String(20))  # Kst
    profit_center = db.Column(db.String(20))  # Kb
    project = db.Column(db.String(20), index=True)  # Proj.
    specification = db.Column(db.String(200))  # Specifikation
    debit = db.Column(db.Float, default=0)  # Debet
    credit = db.Column(db.Float, default=0)  # Kredit

    def to_dict(self):
        return {
            'id': self.id,
            'verification_number': self.verification_number,
            'date': self.date.isoformat() if self.date else None,
            'text': self.text,
            'correction_ref': self.correction_ref,
            'corrected_by': self.corrected_by,
            'preliminary': self.preliminary,
            'account': self.account,
            'account_description': self.account_description,
            'cost_center': self.cost_center,
            'profit_center': self.profit_center,
            'project': self.project,
            'specification': self.specification,
            'debit': self.debit,
            'credit': self.credit,
        }

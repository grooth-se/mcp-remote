from datetime import datetime, timezone
from app.extensions import db


BOARD_ROLE_LABELS = {
    'ordforande': 'Ordförande',
    'ledamot': 'Ledamot',
    'suppleant': 'Suppleant',
    'vd': 'Verkställande direktör',
    'revisor': 'Revisor',
}

MEETING_TYPE_LABELS = {
    'arsstamma': 'Årsstämma',
    'extra_stamma': 'Extra bolagsstämma',
}

ACQUISITION_TYPE_LABELS = {
    'grundande': 'Grundande',
    'kop': 'Köp',
    'nyemission': 'Nyemission',
    'gava': 'Gåva',
}


class BoardMember(db.Model):
    __tablename__ = 'board_members'

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    personal_number = db.Column(db.String(13), nullable=True)
    role = db.Column(db.String(50), nullable=False, default='ledamot')
    title = db.Column(db.String(100), nullable=True)
    appointed_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=True)
    appointed_by = db.Column(db.String(100), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    company = db.relationship('Company', backref='board_members_list')

    @property
    def is_active(self):
        return self.end_date is None

    @property
    def role_label(self):
        return BOARD_ROLE_LABELS.get(self.role, self.role)

    def __repr__(self):
        return f'<BoardMember {self.name} ({self.role})>'


class ShareClass(db.Model):
    __tablename__ = 'share_classes'

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    name = db.Column(db.String(50), nullable=False)
    votes_per_share = db.Column(db.Integer, default=1)
    par_value = db.Column(db.Numeric(10, 2), nullable=True)
    total_shares = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    company = db.relationship('Company', backref='share_classes')
    holdings = db.relationship('ShareholderHolding', backref='share_class',
                               cascade='all, delete-orphan')

    __table_args__ = (
        db.UniqueConstraint('company_id', 'name', name='uq_company_share_class'),
    )

    def __repr__(self):
        return f'<ShareClass {self.name} ({self.total_shares} shares)>'


class Shareholder(db.Model):
    __tablename__ = 'shareholders'

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    personal_or_org_number = db.Column(db.String(20), nullable=True)
    address = db.Column(db.String(300), nullable=True)
    is_company = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    company = db.relationship('Company', backref='shareholders')
    holdings = db.relationship('ShareholderHolding', backref='shareholder',
                               cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Shareholder {self.name}>'


class ShareholderHolding(db.Model):
    __tablename__ = 'shareholder_holdings'

    id = db.Column(db.Integer, primary_key=True)
    shareholder_id = db.Column(db.Integer, db.ForeignKey('shareholders.id'), nullable=False)
    share_class_id = db.Column(db.Integer, db.ForeignKey('share_classes.id'), nullable=False)
    shares = db.Column(db.Integer, nullable=False)
    acquired_date = db.Column(db.Date, nullable=False)
    acquisition_type = db.Column(db.String(30), default='kop')
    price_per_share = db.Column(db.Numeric(15, 2), nullable=True)
    note = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    @property
    def acquisition_label(self):
        return ACQUISITION_TYPE_LABELS.get(self.acquisition_type, self.acquisition_type)

    def __repr__(self):
        return f'<Holding {self.shares} shares>'


class DividendDecision(db.Model):
    __tablename__ = 'dividend_decisions'

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    fiscal_year_id = db.Column(db.Integer, db.ForeignKey('fiscal_years.id'), nullable=False)
    decision_date = db.Column(db.Date, nullable=False)
    total_amount = db.Column(db.Numeric(15, 2), nullable=False)
    amount_per_share = db.Column(db.Numeric(10, 4), nullable=True)
    share_class_id = db.Column(db.Integer, db.ForeignKey('share_classes.id'), nullable=True)
    record_date = db.Column(db.Date, nullable=True)
    payment_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(20), default='beslutad')  # beslutad, betald
    verification_id = db.Column(db.Integer, db.ForeignKey('verifications.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    company = db.relationship('Company', backref='dividend_decisions')
    fiscal_year = db.relationship('FiscalYear', backref='dividend_decisions')
    share_class = db.relationship('ShareClass')
    verification = db.relationship('Verification')

    def __repr__(self):
        return f'<Dividend {self.total_amount} ({self.status})>'


class AGMMinutes(db.Model):
    __tablename__ = 'agm_minutes'

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    meeting_date = db.Column(db.Date, nullable=False)
    meeting_type = db.Column(db.String(30), default='arsstamma')
    fiscal_year_id = db.Column(db.Integer, db.ForeignKey('fiscal_years.id'), nullable=True)
    chairman = db.Column(db.String(200), nullable=True)
    minutes_taker = db.Column(db.String(200), nullable=True)
    resolutions = db.Column(db.Text, nullable=True)
    attendees = db.Column(db.Text, nullable=True)
    document_id = db.Column(db.Integer, db.ForeignKey('documents.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    company = db.relationship('Company', backref='agm_minutes')
    fiscal_year = db.relationship('FiscalYear', backref='agm_minutes')
    document = db.relationship('Document')

    @property
    def meeting_type_label(self):
        return MEETING_TYPE_LABELS.get(self.meeting_type, self.meeting_type)

    def __repr__(self):
        return f'<AGM {self.meeting_date} ({self.meeting_type})>'

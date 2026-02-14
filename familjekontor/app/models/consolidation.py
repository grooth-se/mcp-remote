from datetime import datetime, timezone
from app.extensions import db


CONSOLIDATION_METHOD_LABELS = {
    'full': 'Full konsolidering',
    'equity': 'Kapitalandelsmetoden',
    'cost': 'Anskaffningsvärdemetoden',
}


class ConsolidationGroup(db.Model):
    __tablename__ = 'consolidation_groups'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    parent_company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    description = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    parent_company = db.relationship('Company', backref='consolidation_groups')
    members = db.relationship('ConsolidationGroupMember', backref='group',
                              cascade='all, delete-orphan')
    eliminations = db.relationship('IntercompanyElimination', backref='group',
                                   cascade='all, delete-orphan')
    intercompany_matches = db.relationship('IntercompanyMatch', backref='group',
                                           cascade='all, delete-orphan')
    goodwill_entries = db.relationship('AcquisitionGoodwill', backref='group',
                                       cascade='all, delete-orphan')

    def __repr__(self):
        return f'<ConsolidationGroup {self.name}>'


class ConsolidationGroupMember(db.Model):
    __tablename__ = 'consolidation_group_members'

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('consolidation_groups.id'), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    ownership_pct = db.Column(db.Numeric(5, 2), default=100)
    consolidation_method = db.Column(db.String(20), default='full')
    parent_member_id = db.Column(db.Integer, db.ForeignKey('consolidation_group_members.id'),
                                 nullable=True)

    company = db.relationship('Company', backref='group_memberships')
    parent_member = db.relationship('ConsolidationGroupMember', remote_side='ConsolidationGroupMember.id',
                                    backref='sub_members')

    @property
    def method_label(self):
        return CONSOLIDATION_METHOD_LABELS.get(self.consolidation_method, self.consolidation_method)

    __table_args__ = (
        db.UniqueConstraint('group_id', 'company_id', name='uq_group_company'),
    )

    def __repr__(self):
        return f'<ConsolidationGroupMember {self.company_id} in {self.group_id}>'


class IntercompanyElimination(db.Model):
    __tablename__ = 'intercompany_eliminations'

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('consolidation_groups.id'), nullable=False)
    fiscal_year_id = db.Column(db.Integer, db.ForeignKey('fiscal_years.id'), nullable=False)
    from_company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    to_company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    account_number = db.Column(db.String(10), nullable=False)
    amount = db.Column(db.Numeric(15, 2), nullable=False)
    description = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    fiscal_year = db.relationship('FiscalYear', backref='eliminations')
    from_company = db.relationship('Company', foreign_keys=[from_company_id])
    to_company = db.relationship('Company', foreign_keys=[to_company_id])

    def __repr__(self):
        return f'<Elimination {self.from_company_id}->{self.to_company_id} {self.amount}>'


class IntercompanyMatch(db.Model):
    __tablename__ = 'intercompany_matches'

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('consolidation_groups.id'), nullable=False)
    fiscal_year_id = db.Column(db.Integer, db.ForeignKey('fiscal_years.id'), nullable=False)
    company_a_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    company_b_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    amount = db.Column(db.Numeric(15, 2), nullable=False)
    match_type = db.Column(db.String(30), nullable=True)  # invoice / payment / loan
    description = db.Column(db.String(500), nullable=True)
    status = db.Column(db.String(20), default='suggested')  # suggested / confirmed / rejected
    elimination_id = db.Column(db.Integer, db.ForeignKey('intercompany_eliminations.id'),
                               nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    company_a = db.relationship('Company', foreign_keys=[company_a_id])
    company_b = db.relationship('Company', foreign_keys=[company_b_id])
    elimination = db.relationship('IntercompanyElimination')

    def __repr__(self):
        return f'<IntercompanyMatch {self.company_a_id}<->{self.company_b_id} {self.amount}>'


class AcquisitionGoodwill(db.Model):
    __tablename__ = 'acquisition_goodwill'

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('consolidation_groups.id'), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    acquisition_date = db.Column(db.Date, nullable=False)
    purchase_price = db.Column(db.Numeric(15, 2), nullable=False)
    net_assets_at_acquisition = db.Column(db.Numeric(15, 2), nullable=False)
    goodwill_amount = db.Column(db.Numeric(15, 2), nullable=False)
    amortization_period_months = db.Column(db.Integer, default=60)  # K2 max 5 years
    accumulated_amortization = db.Column(db.Numeric(15, 2), default=0)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    company = db.relationship('Company', backref='goodwill_entries')

    @property
    def monthly_amortization(self):
        if not self.amortization_period_months:
            return 0
        return float(self.goodwill_amount) / self.amortization_period_months

    @property
    def remaining_goodwill(self):
        return float(self.goodwill_amount) - float(self.accumulated_amortization or 0)

    def __repr__(self):
        return f'<AcquisitionGoodwill {self.company_id} {self.goodwill_amount}>'

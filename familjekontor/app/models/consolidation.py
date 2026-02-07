from datetime import datetime, timezone
from app.extensions import db


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

    def __repr__(self):
        return f'<ConsolidationGroup {self.name}>'


class ConsolidationGroupMember(db.Model):
    __tablename__ = 'consolidation_group_members'

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('consolidation_groups.id'), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    ownership_pct = db.Column(db.Numeric(5, 2), default=100)

    company = db.relationship('Company', backref='group_memberships')

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

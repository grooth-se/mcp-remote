"""Governance service: board members, shareholders, dividends, AGM."""

from decimal import Decimal
from sqlalchemy import func
from app.extensions import db
from app.models.governance import (
    BoardMember, ShareClass, Shareholder, ShareholderHolding,
    DividendDecision, AGMMinutes,
)
from app.models.accounting import FiscalYear, Account
from app.models.audit import AuditLog
from app.services.accounting_service import create_verification


# ---------------------------------------------------------------------------
# Board Members
# ---------------------------------------------------------------------------

def create_board_member(company_id, data, created_by=None):
    """Create a board member."""
    member = BoardMember(
        company_id=company_id,
        name=data['name'],
        personal_number=data.get('personal_number'),
        role=data.get('role', 'ledamot'),
        title=data.get('title'),
        appointed_date=data['appointed_date'],
        end_date=data.get('end_date'),
        appointed_by=data.get('appointed_by'),
        email=data.get('email'),
        phone=data.get('phone'),
    )
    db.session.add(member)

    audit = AuditLog(
        company_id=company_id, user_id=created_by,
        action='create', entity_type='board_member', entity_id=0,
        new_values={'name': member.name, 'role': member.role},
    )
    db.session.add(audit)
    db.session.commit()

    audit.entity_id = member.id
    db.session.commit()
    return member


def update_board_member(member_id, data):
    """Update a board member."""
    member = db.session.get(BoardMember, member_id)
    if not member:
        raise ValueError('Styrelseledamot hittades inte')

    for field in ('name', 'personal_number', 'role', 'title', 'appointed_date',
                  'end_date', 'appointed_by', 'email', 'phone'):
        if field in data:
            setattr(member, field, data[field])

    db.session.commit()
    return member


def end_appointment(member_id, end_date):
    """End a board member's appointment."""
    member = db.session.get(BoardMember, member_id)
    if not member:
        raise ValueError('Styrelseledamot hittades inte')
    member.end_date = end_date
    db.session.commit()
    return member


def get_board_members(company_id, active_only=True):
    """List board members, optionally only active."""
    q = BoardMember.query.filter_by(company_id=company_id)
    if active_only:
        q = q.filter(BoardMember.end_date.is_(None))
    return q.order_by(BoardMember.role, BoardMember.name).all()


def get_board_for_annual_report(company_id, fiscal_year_id):
    """Get board members active during a fiscal year, for annual report."""
    fy = db.session.get(FiscalYear, fiscal_year_id)
    if not fy:
        return []

    members = BoardMember.query.filter(
        BoardMember.company_id == company_id,
        BoardMember.appointed_date <= fy.end_date,
        db.or_(
            BoardMember.end_date.is_(None),
            BoardMember.end_date >= fy.start_date,
        ),
    ).order_by(BoardMember.role, BoardMember.name).all()
    return members


# ---------------------------------------------------------------------------
# Share Classes
# ---------------------------------------------------------------------------

def create_share_class(company_id, data, created_by=None):
    """Create a share class."""
    sc = ShareClass(
        company_id=company_id,
        name=data['name'],
        votes_per_share=data.get('votes_per_share', 1),
        par_value=Decimal(str(data['par_value'])) if data.get('par_value') else None,
        total_shares=data['total_shares'],
    )
    db.session.add(sc)

    audit = AuditLog(
        company_id=company_id, user_id=created_by,
        action='create', entity_type='share_class', entity_id=0,
        new_values={'name': sc.name, 'total_shares': sc.total_shares},
    )
    db.session.add(audit)
    db.session.commit()

    audit.entity_id = sc.id
    db.session.commit()
    return sc


def get_share_classes(company_id):
    """List share classes."""
    return ShareClass.query.filter_by(company_id=company_id).order_by(ShareClass.name).all()


# ---------------------------------------------------------------------------
# Shareholders
# ---------------------------------------------------------------------------

def create_shareholder(company_id, data, created_by=None):
    """Create a shareholder."""
    sh = Shareholder(
        company_id=company_id,
        name=data['name'],
        personal_or_org_number=data.get('personal_or_org_number'),
        address=data.get('address'),
        is_company=data.get('is_company', False),
    )
    db.session.add(sh)

    audit = AuditLog(
        company_id=company_id, user_id=created_by,
        action='create', entity_type='shareholder', entity_id=0,
        new_values={'name': sh.name},
    )
    db.session.add(audit)
    db.session.commit()

    audit.entity_id = sh.id
    db.session.commit()
    return sh


def get_shareholders(company_id):
    """List shareholders."""
    return Shareholder.query.filter_by(company_id=company_id).order_by(Shareholder.name).all()


# ---------------------------------------------------------------------------
# Holdings
# ---------------------------------------------------------------------------

def add_holding(shareholder_id, data, created_by=None):
    """Add a shareholding record."""
    shareholder = db.session.get(Shareholder, shareholder_id)
    if not shareholder:
        raise ValueError('Aktieägare hittades inte')

    holding = ShareholderHolding(
        shareholder_id=shareholder_id,
        share_class_id=data['share_class_id'],
        shares=data['shares'],
        acquired_date=data['acquired_date'],
        acquisition_type=data.get('acquisition_type', 'kop'),
        price_per_share=Decimal(str(data['price_per_share'])) if data.get('price_per_share') else None,
        note=data.get('note'),
    )
    db.session.add(holding)
    db.session.commit()
    return holding


def get_ownership_summary(company_id):
    """Calculate ownership summary: shares, percentage, votes per shareholder.

    Returns list of dicts: {shareholder, shares_by_class, total_shares, total_votes, pct}
    """
    shareholders = Shareholder.query.filter_by(company_id=company_id).all()
    share_classes = ShareClass.query.filter_by(company_id=company_id).all()

    total_all_shares = sum(sc.total_shares for sc in share_classes) if share_classes else 0
    total_all_votes = sum(sc.total_shares * sc.votes_per_share for sc in share_classes) if share_classes else 0

    summary = []
    for sh in shareholders:
        shares_by_class = {}
        total_shares = 0
        total_votes = 0

        for holding in sh.holdings:
            sc = holding.share_class
            cls_name = sc.name
            shares_by_class[cls_name] = shares_by_class.get(cls_name, 0) + holding.shares
            total_shares += holding.shares
            total_votes += holding.shares * sc.votes_per_share

        if total_shares > 0:
            pct = (total_shares / total_all_shares * 100) if total_all_shares > 0 else 0
            vote_pct = (total_votes / total_all_votes * 100) if total_all_votes > 0 else 0
            summary.append({
                'shareholder': sh,
                'shares_by_class': shares_by_class,
                'total_shares': total_shares,
                'total_votes': total_votes,
                'pct': round(pct, 2),
                'vote_pct': round(vote_pct, 2),
            })

    summary.sort(key=lambda x: x['total_shares'], reverse=True)
    return summary


def get_share_register(company_id):
    """Get full share register (aktiebok) data.

    Returns list of dicts suitable for aktiebok display.
    """
    shareholders = Shareholder.query.filter_by(company_id=company_id).all()

    register = []
    for sh in shareholders:
        for holding in sh.holdings:
            register.append({
                'shareholder': sh,
                'share_class': holding.share_class,
                'shares': holding.shares,
                'acquired_date': holding.acquired_date,
                'acquisition_type': holding.acquisition_label,
                'price_per_share': holding.price_per_share,
                'note': holding.note,
            })

    register.sort(key=lambda x: (x['shareholder'].name, x['share_class'].name))
    return register


# ---------------------------------------------------------------------------
# Dividends
# ---------------------------------------------------------------------------

def _ensure_account(company_id, account_number, name, account_type):
    """Get or create a BAS account."""
    account = Account.query.filter_by(
        company_id=company_id, account_number=account_number
    ).first()
    if not account:
        account = Account(
            company_id=company_id, account_number=account_number,
            name=name, account_type=account_type, active=True,
        )
        db.session.add(account)
        db.session.flush()
    return account


def create_dividend_decision(company_id, data, created_by=None):
    """Create a dividend decision. Books Debit 2091, Credit 2898."""
    div = DividendDecision(
        company_id=company_id,
        fiscal_year_id=data['fiscal_year_id'],
        decision_date=data['decision_date'],
        total_amount=Decimal(str(data['total_amount'])),
        amount_per_share=Decimal(str(data['amount_per_share'])) if data.get('amount_per_share') else None,
        share_class_id=data.get('share_class_id'),
        record_date=data.get('record_date'),
        payment_date=data.get('payment_date'),
        status='beslutad',
    )
    db.session.add(div)

    audit = AuditLog(
        company_id=company_id, user_id=created_by,
        action='create', entity_type='dividend_decision', entity_id=0,
        new_values={'total_amount': float(div.total_amount)},
    )
    db.session.add(audit)
    db.session.commit()

    audit.entity_id = div.id
    db.session.commit()
    return div


def pay_dividend(decision_id, fiscal_year_id, created_by=None):
    """Pay a dividend: create verification Debit 2898, Credit 1930."""
    div = db.session.get(DividendDecision, decision_id)
    if not div:
        raise ValueError('Utdelningsbeslut hittades inte')
    if div.status == 'betald':
        raise ValueError('Utdelningen är redan betald')

    acct_2898 = _ensure_account(div.company_id, '2898', 'Outtagen utdelning', 'liability')
    acct_1930 = _ensure_account(div.company_id, '1930', 'Företagskonto', 'asset')

    ver_rows = [
        {'account_id': acct_2898.id, 'debit': float(div.total_amount), 'credit': 0},
        {'account_id': acct_1930.id, 'debit': 0, 'credit': float(div.total_amount)},
    ]

    verification = create_verification(
        company_id=div.company_id,
        fiscal_year_id=fiscal_year_id,
        verification_date=div.payment_date or div.decision_date,
        description=f'Utdelning — betalning {float(div.total_amount):,.2f} kr',
        rows=ver_rows,
        verification_type='dividend',
        created_by=created_by,
        source='dividend',
    )

    div.status = 'betald'
    div.verification_id = verification.id

    audit = AuditLog(
        company_id=div.company_id, user_id=created_by,
        action='update', entity_type='dividend_decision', entity_id=div.id,
        new_values={'status': 'betald', 'verification_id': verification.id},
    )
    db.session.add(audit)
    db.session.commit()
    return div


def get_dividends(company_id):
    """List dividend decisions."""
    return DividendDecision.query.filter_by(
        company_id=company_id
    ).order_by(DividendDecision.decision_date.desc()).all()


# ---------------------------------------------------------------------------
# AGM Minutes
# ---------------------------------------------------------------------------

def create_agm_minutes(company_id, data, created_by=None):
    """Create AGM minutes record."""
    agm = AGMMinutes(
        company_id=company_id,
        meeting_date=data['meeting_date'],
        meeting_type=data.get('meeting_type', 'arsstamma'),
        fiscal_year_id=data.get('fiscal_year_id'),
        chairman=data.get('chairman'),
        minutes_taker=data.get('minutes_taker'),
        resolutions=data.get('resolutions'),
        attendees=data.get('attendees'),
        document_id=data.get('document_id'),
    )
    db.session.add(agm)

    audit = AuditLog(
        company_id=company_id, user_id=created_by,
        action='create', entity_type='agm_minutes', entity_id=0,
        new_values={'meeting_date': str(agm.meeting_date), 'meeting_type': agm.meeting_type},
    )
    db.session.add(audit)
    db.session.commit()

    audit.entity_id = agm.id
    db.session.commit()
    return agm


def get_agm_history(company_id):
    """List AGM minutes."""
    return AGMMinutes.query.filter_by(
        company_id=company_id
    ).order_by(AGMMinutes.meeting_date.desc()).all()


def get_agm(agm_id):
    """Get single AGM minutes."""
    return db.session.get(AGMMinutes, agm_id)

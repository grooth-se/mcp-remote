"""Accounting service for verifications, trial balance, and fiscal year operations."""

from datetime import date
from decimal import Decimal
from sqlalchemy import func
from app.extensions import db
from app.models.accounting import FiscalYear, Account, Verification, VerificationRow


def get_next_verification_number(company_id, fiscal_year_id):
    """Get next available verification number for a company/fiscal year."""
    max_num = db.session.query(func.max(Verification.verification_number)).filter_by(
        company_id=company_id, fiscal_year_id=fiscal_year_id
    ).scalar()
    return (max_num or 0) + 1


def create_verification(company_id, fiscal_year_id, verification_date, description,
                        rows, verification_type='manual', created_by=None, source='manual'):
    """Create a verification with rows.

    rows: list of dicts with keys: account_id, debit, credit, description, cost_center
    Returns the created Verification or raises ValueError if unbalanced.
    """
    total_debit = sum(Decimal(str(r.get('debit', 0) or 0)) for r in rows)
    total_credit = sum(Decimal(str(r.get('credit', 0) or 0)) for r in rows)

    if abs(total_debit - total_credit) >= Decimal('0.01'):
        raise ValueError(
            f'Verifikationen balanserar inte: debet {total_debit}, kredit {total_credit}'
        )

    if not rows:
        raise ValueError('Verifikationen måste ha minst en rad')

    ver_number = get_next_verification_number(company_id, fiscal_year_id)

    verification = Verification(
        company_id=company_id,
        fiscal_year_id=fiscal_year_id,
        verification_number=ver_number,
        verification_date=verification_date,
        description=description,
        verification_type=verification_type,
        source=source,
        created_by=created_by,
    )
    db.session.add(verification)
    db.session.flush()

    for r in rows:
        row = VerificationRow(
            verification_id=verification.id,
            account_id=r['account_id'],
            debit=Decimal(str(r.get('debit', 0) or 0)),
            credit=Decimal(str(r.get('credit', 0) or 0)),
            description=r.get('description', ''),
            cost_center=r.get('cost_center', ''),
        )
        db.session.add(row)

    db.session.commit()
    return verification


def get_trial_balance(company_id, fiscal_year_id):
    """Calculate trial balance (råbalans) for a fiscal year.

    Returns list of dicts: account_number, account_name, total_debit, total_credit, balance
    """
    results = db.session.query(
        Account.account_number,
        Account.name,
        Account.account_type,
        func.coalesce(func.sum(VerificationRow.debit), 0).label('total_debit'),
        func.coalesce(func.sum(VerificationRow.credit), 0).label('total_credit'),
    ).join(
        VerificationRow, VerificationRow.account_id == Account.id
    ).join(
        Verification, Verification.id == VerificationRow.verification_id
    ).filter(
        Account.company_id == company_id,
        Verification.fiscal_year_id == fiscal_year_id,
    ).group_by(
        Account.account_number, Account.name, Account.account_type
    ).order_by(
        Account.account_number
    ).all()

    trial_balance = []
    for r in results:
        balance = r.total_debit - r.total_credit
        trial_balance.append({
            'account_number': r.account_number,
            'account_name': r.name,
            'account_type': r.account_type,
            'total_debit': float(r.total_debit),
            'total_credit': float(r.total_credit),
            'balance': float(balance),
        })

    return trial_balance


def get_account_balance(company_id, fiscal_year_id, account_number):
    """Get the balance for a specific account in a fiscal year."""
    account = Account.query.filter_by(
        company_id=company_id, account_number=account_number
    ).first()
    if not account:
        return Decimal('0')

    result = db.session.query(
        func.coalesce(func.sum(VerificationRow.debit), 0).label('total_debit'),
        func.coalesce(func.sum(VerificationRow.credit), 0).label('total_credit'),
    ).join(
        Verification, Verification.id == VerificationRow.verification_id
    ).filter(
        VerificationRow.account_id == account.id,
        Verification.fiscal_year_id == fiscal_year_id,
    ).first()

    return result.total_debit - result.total_credit


def close_fiscal_year(company_id, fiscal_year_id):
    """Close a fiscal year and create opening balances for next year."""
    fy = db.session.get(FiscalYear, fiscal_year_id)
    if not fy or fy.company_id != company_id:
        raise ValueError('Räkenskapsår hittades inte')
    if fy.status == 'closed':
        raise ValueError('Räkenskapsåret är redan stängt')

    # Calculate closing balances for balance sheet accounts (1xxx-2xxx)
    trial = get_trial_balance(company_id, fiscal_year_id)
    balance_accounts = [t for t in trial if t['account_number'][0] in ('1', '2')]
    result_accounts = [t for t in trial if t['account_number'][0] in ('3', '4', '5', '6', '7', '8')]

    # Calculate year's result
    year_result = sum(t['balance'] for t in result_accounts)

    fy.status = 'closed'
    db.session.commit()

    return {
        'balance_accounts': balance_accounts,
        'result_accounts': result_accounts,
        'year_result': year_result,
    }

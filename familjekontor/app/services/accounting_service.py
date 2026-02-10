"""Accounting service for verifications, trial balance, and fiscal year operations."""

from datetime import date, timedelta
from decimal import Decimal
from sqlalchemy import func
from app.extensions import db
from app.models.accounting import FiscalYear, Account, Verification, VerificationRow
from app.models.audit import AuditLog


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
    # Check that the fiscal year is open
    fy = db.session.get(FiscalYear, fiscal_year_id)
    if fy and fy.status == 'closed':
        raise ValueError('Kan inte skapa verifikation i ett stängt räkenskapsår')

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
            currency=r.get('currency'),
            foreign_amount_debit=Decimal(str(r['foreign_amount_debit'])) if r.get('foreign_amount_debit') else None,
            foreign_amount_credit=Decimal(str(r['foreign_amount_credit'])) if r.get('foreign_amount_credit') else None,
            exchange_rate=Decimal(str(r['exchange_rate'])) if r.get('exchange_rate') else None,
        )
        db.session.add(row)

    db.session.commit()
    return verification


def _create_verification_no_lock_check(company_id, fiscal_year_id, verification_date,
                                       description, rows, verification_type='manual',
                                       created_by=None, source='manual'):
    """Internal: create verification without fiscal year lock check (used during closing)."""
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
            currency=r.get('currency'),
            foreign_amount_debit=Decimal(str(r['foreign_amount_debit'])) if r.get('foreign_amount_debit') else None,
            foreign_amount_credit=Decimal(str(r['foreign_amount_credit'])) if r.get('foreign_amount_credit') else None,
            exchange_rate=Decimal(str(r['exchange_rate'])) if r.get('exchange_rate') else None,
        )
        db.session.add(row)

    db.session.flush()
    return verification


def get_trial_balance(company_id, fiscal_year_id):
    """Calculate trial balance (råbalans) for a fiscal year.

    Returns list of dicts: account_number, account_name, total_debit, total_credit, balance
    """
    results = db.session.query(
        Account.id.label('account_id'),
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
        Account.id, Account.account_number, Account.name, Account.account_type
    ).order_by(
        Account.account_number
    ).all()

    trial_balance = []
    for r in results:
        balance = r.total_debit - r.total_credit
        trial_balance.append({
            'account_id': r.account_id,
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


def preview_closing(company_id, fiscal_year_id):
    """Preview year-end closing without making changes.

    Returns dict with balance_accounts, result_accounts, year_result, fiscal_year.
    """
    fy = db.session.get(FiscalYear, fiscal_year_id)
    if not fy or fy.company_id != company_id:
        raise ValueError('Räkenskapsår hittades inte')

    trial = get_trial_balance(company_id, fiscal_year_id)
    balance_accounts = [t for t in trial if t['account_number'][0] in ('1', '2')]
    result_accounts = [t for t in trial if t['account_number'][0] in ('3', '4', '5', '6', '7', '8')]

    # Year result: negative sum of result account balances
    # Revenue accounts (3xxx) typically have credit balance (negative in debit-credit)
    # Expense accounts (4xxx-8xxx) typically have debit balance (positive)
    # Result = -(sum of result balances) => positive means profit
    year_result = -sum(t['balance'] for t in result_accounts)

    # Split for summary
    revenue = sum(t['balance'] for t in result_accounts if t['account_number'][0] == '3')
    expenses = sum(t['balance'] for t in result_accounts if t['account_number'][0] in ('4', '5', '6', '7', '8'))

    return {
        'balance_accounts': balance_accounts,
        'result_accounts': result_accounts,
        'year_result': year_result,
        'revenue': -revenue,  # positive number
        'expenses': expenses,  # positive number
        'fiscal_year': fy,
    }


def close_fiscal_year(company_id, fiscal_year_id, created_by=None):
    """Close a fiscal year: create closing entries, opening balances, lock FY."""
    fy = db.session.get(FiscalYear, fiscal_year_id)
    if not fy or fy.company_id != company_id:
        raise ValueError('Räkenskapsår hittades inte')
    if fy.status == 'closed':
        raise ValueError('Räkenskapsåret är redan stängt')

    trial = get_trial_balance(company_id, fiscal_year_id)
    balance_accounts = [t for t in trial if t['account_number'][0] in ('1', '2')]
    result_accounts = [t for t in trial if t['account_number'][0] in ('3', '4', '5', '6', '7', '8')]

    year_result = -sum(t['balance'] for t in result_accounts)

    # --- 1. Closing verification: close result accounts to 2099 ---
    account_2099 = Account.query.filter_by(
        company_id=company_id, account_number='2099'
    ).first()
    if not account_2099:
        # Auto-create 2099 if missing
        account_2099 = Account(
            company_id=company_id,
            account_number='2099',
            name='Årets resultat',
            account_type='equity',
        )
        db.session.add(account_2099)
        db.session.flush()

    closing_rows = []
    for t in result_accounts:
        if abs(t['balance']) < 0.01:
            continue
        balance = Decimal(str(t['balance']))
        # Reverse the balance: if debit balance (positive), credit it; if credit balance (negative), debit it
        if balance > 0:
            closing_rows.append({
                'account_id': t['account_id'],
                'debit': 0,
                'credit': float(balance),
            })
        else:
            closing_rows.append({
                'account_id': t['account_id'],
                'debit': float(abs(balance)),
                'credit': 0,
            })

    # Offset to 2099
    if closing_rows:
        total_debit = sum(Decimal(str(r['debit'] or 0)) for r in closing_rows)
        total_credit = sum(Decimal(str(r['credit'] or 0)) for r in closing_rows)
        offset = total_credit - total_debit  # positive means profit (credit to 2099)
        if offset > 0:
            closing_rows.append({
                'account_id': account_2099.id,
                'debit': float(offset),
                'credit': 0,
            })
        elif offset < 0:
            closing_rows.append({
                'account_id': account_2099.id,
                'debit': 0,
                'credit': float(abs(offset)),
            })

        closing_ver = _create_verification_no_lock_check(
            company_id=company_id,
            fiscal_year_id=fiscal_year_id,
            verification_date=fy.end_date,
            description=f'Bokslut — stängning av resultatkonton {fy.year}',
            rows=closing_rows,
            verification_type='closing',
            created_by=created_by,
            source='closing',
        )
    else:
        closing_ver = None

    # --- 2. Create or find next fiscal year ---
    next_fy = FiscalYear.query.filter_by(
        company_id=company_id, year=fy.year + 1
    ).first()
    if not next_fy:
        next_start = fy.end_date + timedelta(days=1)
        next_end = date(fy.end_date.year + 1, fy.end_date.month, fy.end_date.day)
        next_fy = FiscalYear(
            company_id=company_id,
            year=fy.year + 1,
            start_date=next_start,
            end_date=next_end,
            status='open',
        )
        db.session.add(next_fy)
        db.session.flush()

    # --- 3. Opening balance verification in next FY ---
    # Recalculate balance accounts after closing verification
    trial_after = get_trial_balance(company_id, fiscal_year_id)
    balance_after = [t for t in trial_after if t['account_number'][0] in ('1', '2')]

    opening_rows = []
    for t in balance_after:
        if abs(t['balance']) < 0.01:
            continue
        balance = Decimal(str(t['balance']))
        if t['account_number'][0] == '1':
            # Assets: debit if positive balance, credit if negative
            if balance > 0:
                opening_rows.append({
                    'account_id': t['account_id'],
                    'debit': float(balance),
                    'credit': 0,
                })
            else:
                opening_rows.append({
                    'account_id': t['account_id'],
                    'debit': 0,
                    'credit': float(abs(balance)),
                })
        else:
            # Liabilities/equity (2xxx): credit if positive credit balance
            # Balance = debit - credit, so negative balance means credit balance
            if balance < 0:
                opening_rows.append({
                    'account_id': t['account_id'],
                    'debit': 0,
                    'credit': float(abs(balance)),
                })
            elif balance > 0:
                opening_rows.append({
                    'account_id': t['account_id'],
                    'debit': float(balance),
                    'credit': 0,
                })

    opening_ver = None
    if opening_rows:
        opening_ver = _create_verification_no_lock_check(
            company_id=company_id,
            fiscal_year_id=next_fy.id,
            verification_date=next_fy.start_date,
            description=f'Ingående balanser från {fy.year}',
            rows=opening_rows,
            verification_type='opening',
            created_by=created_by,
            source='opening',
        )

    # --- 4. Lock the fiscal year ---
    fy.status = 'closed'

    # --- 5. Audit log ---
    audit = AuditLog(
        company_id=company_id,
        user_id=created_by,
        action='close',
        entity_type='fiscal_year',
        entity_id=fy.id,
        new_values={'year': fy.year, 'year_result': float(year_result)},
    )
    db.session.add(audit)

    db.session.commit()

    return {
        'balance_accounts': balance_after,
        'result_accounts': result_accounts,
        'year_result': year_result,
        'closing_verification': closing_ver,
        'opening_verification': opening_ver,
        'next_fiscal_year': next_fy,
    }

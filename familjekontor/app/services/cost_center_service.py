"""Cost center service: CRUD and P&L reports by cost center."""

from decimal import Decimal

from app.extensions import db
from app.models.cost_center import CostCenter
from app.models.accounting import Account, Verification, VerificationRow, FiscalYear


def get_cost_centers(company_id, active_only=True):
    """Get all cost centers for a company."""
    query = CostCenter.query.filter_by(company_id=company_id)
    if active_only:
        query = query.filter_by(active=True)
    return query.order_by(CostCenter.code).all()


def create_cost_center(company_id, code, name):
    """Create a new cost center. Returns the created object."""
    cc = CostCenter(company_id=company_id, code=code.strip(), name=name.strip())
    db.session.add(cc)
    db.session.commit()
    return cc


def update_cost_center(cost_center_id, **kwargs):
    """Update a cost center's fields."""
    cc = db.session.get(CostCenter, cost_center_id)
    if not cc:
        return None
    for key in ('code', 'name', 'active'):
        if key in kwargs:
            setattr(cc, key, kwargs[key])
    db.session.commit()
    return cc


def delete_cost_center(cost_center_id):
    """Soft-delete a cost center (set active=False)."""
    cc = db.session.get(CostCenter, cost_center_id)
    if not cc:
        return False
    cc.active = False
    db.session.commit()
    return True


def get_cost_center_pnl(company_id, fiscal_year_id, cost_center_code):
    """Get P&L data filtered by a specific cost center.

    Queries VerificationRow where cost_center matches the given code,
    grouping by account for revenue (3xxx) and expense (4-8xxx) accounts.

    Returns dict with revenue_lines, expense_lines, total_revenue,
    total_expenses, result.
    """
    rows = (db.session.query(
        Account.account_number,
        Account.name,
        db.func.sum(VerificationRow.debit).label('total_debit'),
        db.func.sum(VerificationRow.credit).label('total_credit'),
    )
    .join(VerificationRow, VerificationRow.account_id == Account.id)
    .join(Verification, Verification.id == VerificationRow.verification_id)
    .filter(
        Verification.company_id == company_id,
        Verification.fiscal_year_id == fiscal_year_id,
        VerificationRow.cost_center == cost_center_code,
        Account.account_number >= '3000',
        Account.account_number <= '8999',
    )
    .group_by(Account.account_number, Account.name)
    .order_by(Account.account_number)
    .all())

    revenue_lines = []
    expense_lines = []
    total_revenue = Decimal('0')
    total_expenses = Decimal('0')

    for acct_num, acct_name, total_debit, total_credit in rows:
        debit = Decimal(str(total_debit or 0))
        credit = Decimal(str(total_credit or 0))

        if acct_num < '4000':
            # Revenue: credit - debit
            amount = credit - debit
            revenue_lines.append({
                'account_number': acct_num,
                'account_name': acct_name,
                'amount': float(amount),
            })
            total_revenue += amount
        else:
            # Expense: debit - credit
            amount = debit - credit
            expense_lines.append({
                'account_number': acct_num,
                'account_name': acct_name,
                'amount': float(amount),
            })
            total_expenses += amount

    return {
        'revenue_lines': revenue_lines,
        'expense_lines': expense_lines,
        'total_revenue': float(total_revenue),
        'total_expenses': float(total_expenses),
        'result': float(total_revenue - total_expenses),
    }


def get_all_cost_centers_pnl(company_id, fiscal_year_id):
    """Get a summary P&L for all cost centers at once.

    Returns list of dicts: [{code, name, revenue, expenses, result}].
    """
    cost_centers = get_cost_centers(company_id, active_only=False)
    summaries = []

    for cc in cost_centers:
        pnl = get_cost_center_pnl(company_id, fiscal_year_id, cc.code)
        summaries.append({
            'code': cc.code,
            'name': cc.name,
            'active': cc.active,
            'revenue': pnl['total_revenue'],
            'expenses': pnl['total_expenses'],
            'result': pnl['result'],
        })

    return summaries

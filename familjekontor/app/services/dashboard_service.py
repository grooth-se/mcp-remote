"""Dashboard analytics service: KPIs, charts, multi-company overview."""

from datetime import date, timedelta
from decimal import Decimal
from sqlalchemy import func

from app.extensions import db
from app.models.company import Company
from app.models.accounting import FiscalYear, Account, Verification, VerificationRow
from app.models.invoice import SupplierInvoice, CustomerInvoice
from app.models.salary import SalaryRun


def get_multi_company_overview():
    """Get summary stats for all active companies."""
    companies = Company.query.filter_by(active=True).order_by(Company.name).all()
    result = []
    for co in companies:
        active_fy = FiscalYear.query.filter_by(
            company_id=co.id, status='open'
        ).order_by(FiscalYear.year.desc()).first()

        ver_count = 0
        if active_fy:
            ver_count = Verification.query.filter_by(
                company_id=co.id, fiscal_year_id=active_fy.id
            ).count()

        pending_supplier = SupplierInvoice.query.filter_by(
            company_id=co.id, status='pending'
        ).count()

        unpaid_customer = CustomerInvoice.query.filter(
            CustomerInvoice.company_id == co.id,
            CustomerInvoice.status.in_(['sent', 'overdue'])
        ).count()

        result.append({
            'company': co,
            'fiscal_year': active_fy,
            'verification_count': ver_count,
            'pending_supplier': pending_supplier,
            'unpaid_customer': unpaid_customer,
        })
    return result


def get_revenue_expense_trend(company_id, fiscal_year_id):
    """Monthly revenue and expense data for Chart.js bar chart."""
    fy = db.session.get(FiscalYear, fiscal_year_id)
    if not fy:
        return {'labels': [], 'revenue': [], 'expenses': []}

    month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'Maj', 'Jun',
                   'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dec']

    labels = []
    revenue = []
    expenses = []

    for month in range(1, 13):
        labels.append(month_names[month - 1])

        # Revenue: credit on 3xxx accounts
        rev_result = db.session.query(
            func.coalesce(func.sum(VerificationRow.credit - VerificationRow.debit), 0)
        ).join(
            Verification, Verification.id == VerificationRow.verification_id
        ).join(
            Account, Account.id == VerificationRow.account_id
        ).filter(
            Verification.company_id == company_id,
            Verification.fiscal_year_id == fiscal_year_id,
            func.extract('month', Verification.verification_date) == month,
            Account.account_number.like('3%'),
        ).scalar()

        # Expenses: debit on 4xxx-7xxx accounts
        exp_result = db.session.query(
            func.coalesce(func.sum(VerificationRow.debit - VerificationRow.credit), 0)
        ).join(
            Verification, Verification.id == VerificationRow.verification_id
        ).join(
            Account, Account.id == VerificationRow.account_id
        ).filter(
            Verification.company_id == company_id,
            Verification.fiscal_year_id == fiscal_year_id,
            func.extract('month', Verification.verification_date) == month,
            Account.account_number.like('4%') |
            Account.account_number.like('5%') |
            Account.account_number.like('6%') |
            Account.account_number.like('7%'),
        ).scalar()

        revenue.append(float(rev_result or 0))
        expenses.append(float(exp_result or 0))

    return {'labels': labels, 'revenue': revenue, 'expenses': expenses}


def get_cash_flow_data(company_id, fiscal_year_id):
    """Monthly cash flow data for Chart.js line chart."""
    fy = db.session.get(FiscalYear, fiscal_year_id)
    if not fy:
        return {'labels': [], 'cash_flow': [], 'balance': []}

    month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'Maj', 'Jun',
                   'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dec']

    labels = []
    cash_flow = []
    balance = []
    running_balance = 0

    for month in range(1, 13):
        labels.append(month_names[month - 1])

        # Cash accounts: 19xx (bank, kassa)
        cf_result = db.session.query(
            func.coalesce(func.sum(VerificationRow.debit - VerificationRow.credit), 0)
        ).join(
            Verification, Verification.id == VerificationRow.verification_id
        ).join(
            Account, Account.id == VerificationRow.account_id
        ).filter(
            Verification.company_id == company_id,
            Verification.fiscal_year_id == fiscal_year_id,
            func.extract('month', Verification.verification_date) == month,
            Account.account_number.like('19%'),
        ).scalar()

        monthly_cf = float(cf_result or 0)
        running_balance += monthly_cf
        cash_flow.append(monthly_cf)
        balance.append(running_balance)

    return {'labels': labels, 'cash_flow': cash_flow, 'balance': balance}


def get_invoice_aging(company_id):
    """Invoice aging buckets for customer invoices."""
    today = date.today()
    buckets = {'current': 0, '1_30': 0, '31_60': 0, '61_90': 0, '90_plus': 0}

    invoices = CustomerInvoice.query.filter(
        CustomerInvoice.company_id == company_id,
        CustomerInvoice.status.in_(['sent', 'overdue']),
    ).all()

    for inv in invoices:
        days_overdue = (today - inv.due_date).days
        amount = float(inv.total_amount or 0)
        if days_overdue <= 0:
            buckets['current'] += amount
        elif days_overdue <= 30:
            buckets['1_30'] += amount
        elif days_overdue <= 60:
            buckets['31_60'] += amount
        elif days_overdue <= 90:
            buckets['61_90'] += amount
        else:
            buckets['90_plus'] += amount

    return buckets


def get_kpi_data(company_id, fiscal_year_id):
    """Key performance indicators."""
    fy = db.session.get(FiscalYear, fiscal_year_id)
    if not fy:
        return None

    today = date.today()
    current_month = today.month

    # Total revenue YTD (credit - debit on 3xxx)
    rev = db.session.query(
        func.coalesce(func.sum(VerificationRow.credit - VerificationRow.debit), 0)
    ).join(
        Verification, Verification.id == VerificationRow.verification_id
    ).join(
        Account, Account.id == VerificationRow.account_id
    ).filter(
        Verification.company_id == company_id,
        Verification.fiscal_year_id == fiscal_year_id,
        Account.account_number.like('3%'),
    ).scalar()
    revenue = float(rev or 0)

    # Total expenses YTD (debit - credit on 4xxx-7xxx)
    exp = db.session.query(
        func.coalesce(func.sum(VerificationRow.debit - VerificationRow.credit), 0)
    ).join(
        Verification, Verification.id == VerificationRow.verification_id
    ).join(
        Account, Account.id == VerificationRow.account_id
    ).filter(
        Verification.company_id == company_id,
        Verification.fiscal_year_id == fiscal_year_id,
        Account.account_number.like('4%') |
        Account.account_number.like('5%') |
        Account.account_number.like('6%') |
        Account.account_number.like('7%'),
    ).scalar()
    expenses = float(exp or 0)

    # Previous month revenue for MoM change
    prev_month = current_month - 1 if current_month > 1 else 12
    prev_rev = db.session.query(
        func.coalesce(func.sum(VerificationRow.credit - VerificationRow.debit), 0)
    ).join(
        Verification, Verification.id == VerificationRow.verification_id
    ).join(
        Account, Account.id == VerificationRow.account_id
    ).filter(
        Verification.company_id == company_id,
        Verification.fiscal_year_id == fiscal_year_id,
        func.extract('month', Verification.verification_date) == prev_month,
        Account.account_number.like('3%'),
    ).scalar()
    prev_revenue = float(prev_rev or 0)

    # MoM change
    mom_change = 0
    if prev_revenue > 0:
        current_rev = db.session.query(
            func.coalesce(func.sum(VerificationRow.credit - VerificationRow.debit), 0)
        ).join(
            Verification, Verification.id == VerificationRow.verification_id
        ).join(
            Account, Account.id == VerificationRow.account_id
        ).filter(
            Verification.company_id == company_id,
            Verification.fiscal_year_id == fiscal_year_id,
            func.extract('month', Verification.verification_date) == current_month,
            Account.account_number.like('3%'),
        ).scalar()
        current_rev_val = float(current_rev or 0)
        mom_change = round(((current_rev_val - prev_revenue) / prev_revenue) * 100, 1)

    # Burn rate (avg monthly expense)
    months_elapsed = max(current_month - fy.start_date.month + 1, 1)
    burn_rate = round(expenses / months_elapsed, 2)

    # Cash balance for runway
    cash = db.session.query(
        func.coalesce(func.sum(VerificationRow.debit - VerificationRow.credit), 0)
    ).join(
        Verification, Verification.id == VerificationRow.verification_id
    ).join(
        Account, Account.id == VerificationRow.account_id
    ).filter(
        Verification.company_id == company_id,
        Verification.fiscal_year_id == fiscal_year_id,
        Account.account_number.like('19%'),
    ).scalar()
    cash_balance = float(cash or 0)

    runway = round(cash_balance / burn_rate, 1) if burn_rate > 0 else None

    return {
        'revenue': revenue,
        'expenses': expenses,
        'prev_revenue': prev_revenue,
        'mom_change': mom_change,
        'burn_rate': burn_rate,
        'runway': runway,
        'cash_balance': cash_balance,
    }


def get_salary_overview(company_id):
    """Latest salary run summary or None."""
    latest = SalaryRun.query.filter_by(
        company_id=company_id
    ).order_by(SalaryRun.period_year.desc(), SalaryRun.period_month.desc()).first()

    if not latest:
        return None

    return {
        'period': latest.period_label,
        'status': latest.status,
        'total_gross': float(latest.total_gross or 0),
        'total_net': float(latest.total_net or 0),
        'total_tax': float(latest.total_tax or 0),
        'total_employer_contributions': float(latest.total_employer_contributions or 0),
        'employee_count': len(latest.entries),
    }


def get_fiscal_year_progress(company_id, fiscal_year_id):
    """Calculate fiscal year progress percentage and days remaining."""
    fy = db.session.get(FiscalYear, fiscal_year_id)
    if not fy:
        return None

    today = date.today()
    total_days = (fy.end_date - fy.start_date).days
    elapsed_days = (today - fy.start_date).days

    if total_days <= 0:
        return {'progress_pct': 100, 'days_remaining': 0}

    progress = min(max(round((elapsed_days / total_days) * 100, 1), 0), 100)
    remaining = max((fy.end_date - today).days, 0)

    return {'progress_pct': progress, 'days_remaining': remaining}

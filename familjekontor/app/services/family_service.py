"""Family Office aggregation service (Phase 8).

Cross-company views that aggregate data from ALL active companies.
No database migration — everything is computed on-the-fly.
"""

from datetime import date, timedelta
from decimal import Decimal

from app.extensions import db
from app.models.company import Company
from app.models.accounting import FiscalYear
from app.models.audit import AuditLog
from app.models.notification import Notification
from app.models.tax import Deadline


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _get_companies_with_fy():
    """Return list of (company, active_fiscal_year) for all active companies."""
    companies = Company.query.filter_by(active=True).order_by(Company.name).all()
    result = []
    for co in companies:
        fy = FiscalYear.query.filter_by(company_id=co.id, status='open') \
            .order_by(FiscalYear.year.desc()).first()
        if fy:
            result.append((co, fy))
    return result


# ---------------------------------------------------------------------------
# 8A — Family Dashboard
# ---------------------------------------------------------------------------

def get_family_dashboard_data():
    """Aggregate KPIs across all active companies.

    Returns dict with total_cash, total_revenue_ytd, total_expenses_ytd,
    company_count, and per_company list.
    """
    from app.services.dashboard_service import get_kpi_data

    pairs = _get_companies_with_fy()
    total_cash = 0.0
    total_revenue = 0.0
    total_expenses = 0.0
    per_company = []

    for co, fy in pairs:
        try:
            kpi = get_kpi_data(co.id, fy.id)
        except Exception:
            kpi = {'revenue': 0, 'expenses': 0, 'cash_balance': 0}

        revenue = float(kpi.get('revenue') or 0)
        expenses = float(kpi.get('expenses') or 0)
        cash = float(kpi.get('cash_balance') or 0)

        total_cash += cash
        total_revenue += revenue
        total_expenses += expenses

        per_company.append({
            'company': co,
            'fiscal_year': fy,
            'kpi': kpi,
            'cash': cash,
            'revenue': revenue,
            'expenses': expenses,
        })

    return {
        'total_cash': total_cash,
        'total_revenue_ytd': total_revenue,
        'total_expenses_ytd': total_expenses,
        'company_count': len(pairs),
        'per_company': per_company,
    }


def get_family_revenue_trend():
    """Monthly revenue/expense per company for stacked chart.

    Returns dict with labels, datasets (per company), and totals.
    """
    from app.services.dashboard_service import get_revenue_expense_trend

    pairs = _get_companies_with_fy()
    datasets = []
    all_labels = []

    for co, fy in pairs:
        try:
            trend = get_revenue_expense_trend(co.id, fy.id)
        except Exception:
            continue
        labels = trend.get('labels', [])
        if len(labels) > len(all_labels):
            all_labels = labels
        datasets.append({
            'company_name': co.name,
            'revenue': trend.get('revenue', []),
            'expenses': trend.get('expenses', []),
        })

    # Compute totals across companies
    max_len = len(all_labels)
    total_revenue = [0.0] * max_len
    total_expenses = [0.0] * max_len
    for ds in datasets:
        for i, val in enumerate(ds['revenue'][:max_len]):
            total_revenue[i] += float(val or 0)
        for i, val in enumerate(ds['expenses'][:max_len]):
            total_expenses[i] += float(val or 0)

    return {
        'labels': all_labels,
        'datasets': datasets,
        'totals': {'revenue': total_revenue, 'expenses': total_expenses},
    }


def get_family_health_indicators():
    """Key financial ratios per company with traffic-light status.

    Returns list of dicts with company, overall_status, ratios.
    """
    from app.services.ratio_service import get_ratio_summary

    KEY_RATIOS = {'operating_margin', 'current_ratio', 'equity_ratio'}
    pairs = _get_companies_with_fy()
    result = []

    for co, fy in pairs:
        try:
            summary = get_ratio_summary(co.id, fy.id)
        except Exception:
            summary = []

        picked = []
        for r in summary:
            if r.get('name') in KEY_RATIOS:
                picked.append({
                    'name': r['name'],
                    'label': r.get('label', r['name']),
                    'value': r.get('value'),
                    'status': r.get('status', 'good'),
                })

        statuses = [r['status'] for r in picked]
        if 'danger' in statuses:
            overall = 'danger'
        elif 'warning' in statuses:
            overall = 'warning'
        else:
            overall = 'good'

        result.append({
            'company': co,
            'overall_status': overall,
            'ratios': picked,
        })

    return result


# ---------------------------------------------------------------------------
# 8B — Cross-Company Cash Flow
# ---------------------------------------------------------------------------

def get_cross_company_cashflow():
    """Cash flow data per company for comparison chart.

    Returns dict with labels, per_company list, and totals.
    """
    from app.services.dashboard_service import get_cash_flow_data

    pairs = _get_companies_with_fy()
    per_company = []
    all_labels = []

    for co, fy in pairs:
        try:
            cf = get_cash_flow_data(co.id, fy.id)
        except Exception:
            continue
        labels = cf.get('labels', [])
        if len(labels) > len(all_labels):
            all_labels = labels
        per_company.append({
            'company_name': co.name,
            'cash_flow': cf.get('cash_flow', []),
            'balance': cf.get('balance', []),
        })

    max_len = len(all_labels)
    total_cf = [0.0] * max_len
    total_bal = [0.0] * max_len
    for pc in per_company:
        for i, val in enumerate(pc['cash_flow'][:max_len]):
            total_cf[i] += float(val or 0)
        for i, val in enumerate(pc['balance'][:max_len]):
            total_bal[i] += float(val or 0)

    return {
        'labels': all_labels,
        'per_company': per_company,
        'totals': {'cash_flow': total_cf, 'balance': total_bal},
    }


# ---------------------------------------------------------------------------
# 8C — Family Wealth Summary
# ---------------------------------------------------------------------------

def get_family_wealth_summary():
    """Aggregate wealth across all companies.

    Returns dict with net_worth, allocation percentages,
    total_dividends, and per_company breakdown.
    """
    from app.services.report_service import get_balance_sheet
    from app.services.dashboard_service import get_kpi_data

    pairs = _get_companies_with_fy()
    total_equity = 0.0
    total_investments = 0.0
    total_cash = 0.0
    total_fixed_assets = 0.0
    total_dividends = 0.0
    total_assets = 0.0
    per_company = []

    for co, fy in pairs:
        equity = 0.0
        inv_value = 0.0
        cash = 0.0
        fixed = 0.0
        dividends = 0.0
        co_total_assets = 0.0

        # Balance sheet → equity + total assets
        try:
            bs = get_balance_sheet(co.id, fy.id)
            sections = bs.get('sections', {})
            if 'Eget kapital' in sections:
                equity = float(sections['Eget kapital'].get('total', 0))
            co_total_assets = float(bs.get('total_assets', 0))
        except Exception:
            pass

        # KPI → cash balance
        try:
            kpi = get_kpi_data(co.id, fy.id)
            cash = float(kpi.get('cash_balance') or 0)
        except Exception:
            pass

        # Investment portfolios
        try:
            from app.services.investment_service import get_portfolio_summary
            port = get_portfolio_summary(co.id)
            inv_value = float(port.get('total_value') or 0)
        except Exception:
            pass

        # Dividend income
        try:
            from app.services.investment_service import get_dividend_income_summary
            divs = get_dividend_income_summary(co.id, fy.id)
            dividends = sum(float(d.get('total', 0)) for d in divs)
        except Exception:
            pass

        # Fixed assets
        try:
            from app.services.asset_service import get_assets
            assets = get_assets(co.id, status='active')
            fixed = sum(float(a.purchase_amount or 0) for a in assets)
        except Exception:
            pass

        total_equity += equity
        total_investments += inv_value
        total_cash += cash
        total_fixed_assets += fixed
        total_dividends += dividends
        total_assets += co_total_assets

        per_company.append({
            'company': co,
            'equity': equity,
            'investments': inv_value,
            'cash': cash,
            'fixed_assets': fixed,
            'dividends': dividends,
            'total_assets': co_total_assets,
        })

    # Asset allocation percentages
    grand_total = total_cash + total_investments + total_fixed_assets
    if grand_total > 0:
        allocation = {
            'kassa': round(total_cash / grand_total * 100, 1),
            'värdepapper': round(total_investments / grand_total * 100, 1),
            'fastigheter': round(total_fixed_assets / grand_total * 100, 1),
        }
    else:
        allocation = {'kassa': 0, 'värdepapper': 0, 'fastigheter': 0}

    net_worth = total_equity

    return {
        'net_worth': net_worth,
        'total_equity': total_equity,
        'total_investments': total_investments,
        'total_cash': total_cash,
        'total_fixed_assets': total_fixed_assets,
        'total_dividends': total_dividends,
        'total_assets': total_assets,
        'allocation': allocation,
        'per_company': per_company,
    }


# ---------------------------------------------------------------------------
# 8D — Cross-Company Alerts
# ---------------------------------------------------------------------------

def get_cross_company_alerts(user_id):
    """Notifications across all active companies, sorted by date.

    Returns dict with notifications list and total_unread count.
    """
    from app.services.notification_service import generate_notifications

    companies = Company.query.filter_by(active=True).order_by(Company.name).all()
    total_unread = 0

    for co in companies:
        try:
            generate_notifications(user_id, co.id)
        except Exception:
            pass

    # Query all notifications for this user across all companies
    notifications = (
        Notification.query
        .filter_by(user_id=user_id)
        .order_by(Notification.created_at.desc())
        .limit(30)
        .all()
    )

    total_unread = (
        Notification.query
        .filter_by(user_id=user_id, read=False)
        .count()
    )

    return {
        'notifications': notifications,
        'total_unread': total_unread,
    }


def get_upcoming_deadlines_all(days_ahead=30):
    """Tax deadlines across all companies within date range.

    Returns dict with overdue and upcoming lists.
    """
    today = date.today()
    future = today + timedelta(days=days_ahead)

    # Overdue: past due_date, still pending
    overdue = (
        Deadline.query
        .join(Company)
        .filter(
            Company.active == True,
            Deadline.due_date < today,
            Deadline.status == 'pending',
        )
        .order_by(Deadline.due_date.asc())
        .all()
    )

    # Upcoming: due within days_ahead
    upcoming = (
        Deadline.query
        .join(Company)
        .filter(
            Company.active == True,
            Deadline.due_date >= today,
            Deadline.due_date <= future,
            Deadline.status == 'pending',
        )
        .order_by(Deadline.due_date.asc())
        .all()
    )

    return {
        'overdue': overdue,
        'upcoming': upcoming,
    }


def get_activity_feed(limit=30):
    """Recent audit log entries across all companies.

    Returns list of dicts with timestamp, company_name, action, entity_type, description.
    """
    logs = (
        AuditLog.query
        .order_by(AuditLog.timestamp.desc())
        .limit(limit)
        .all()
    )

    # Build company name lookup
    company_ids = {log.company_id for log in logs if log.company_id}
    companies = {}
    if company_ids:
        for co in Company.query.filter(Company.id.in_(company_ids)).all():
            companies[co.id] = co.name

    result = []
    for log in logs:
        result.append({
            'timestamp': log.timestamp,
            'company_name': companies.get(log.company_id, '-'),
            'action': log.action,
            'entity_type': log.entity_type or '-',
            'entity_id': log.entity_id,
        })

    return result

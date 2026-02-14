"""Family Office routes (Phase 8).

Cross-company views: dashboard, cash flow, wealth summary, alerts.
"""

from flask import Blueprint, render_template, jsonify
from flask_login import login_required, current_user

from app.services.family_service import (
    get_family_dashboard_data,
    get_family_revenue_trend,
    get_family_health_indicators,
    get_cross_company_cashflow,
    get_family_wealth_summary,
    get_cross_company_alerts,
    get_upcoming_deadlines_all,
    get_activity_feed,
)

family_bp = Blueprint('family', __name__)


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------

@family_bp.route('/')
@login_required
def index():
    """8A — Family Office Dashboard."""
    data = get_family_dashboard_data()
    health = get_family_health_indicators()
    return render_template('family/dashboard.html', data=data, health=health)


@family_bp.route('/cashflow')
@login_required
def cashflow():
    """8B — Cross-Company Cash Flow."""
    data = get_cross_company_cashflow()
    return render_template('family/cashflow.html', data=data)


@family_bp.route('/wealth')
@login_required
def wealth():
    """8C — Family Wealth Summary."""
    data = get_family_wealth_summary()
    return render_template('family/wealth.html', data=data)


@family_bp.route('/alerts')
@login_required
def alerts():
    """8D — Cross-Company Alerts."""
    alert_data = get_cross_company_alerts(current_user.id)
    deadlines = get_upcoming_deadlines_all()
    activity = get_activity_feed()
    return render_template(
        'family/alerts.html',
        alert_data=alert_data,
        deadlines=deadlines,
        activity=activity,
    )


# ---------------------------------------------------------------------------
# JSON API routes (for Chart.js)
# ---------------------------------------------------------------------------

@family_bp.route('/api/revenue-trend')
@login_required
def api_revenue_trend():
    """JSON: monthly revenue/expense per company for stacked bar chart."""
    data = get_family_revenue_trend()
    # Serialise for JSON (company objects not included)
    return jsonify({
        'labels': data['labels'],
        'datasets': data['datasets'],
        'totals': data['totals'],
    })


@family_bp.route('/api/cash-position')
@login_required
def api_cash_position():
    """JSON: cash balance timeline per company for line chart."""
    data = get_cross_company_cashflow()
    return jsonify({
        'labels': data['labels'],
        'per_company': data['per_company'],
        'totals': data['totals'],
    })


@family_bp.route('/api/cashflow-comparison')
@login_required
def api_cashflow_comparison():
    """JSON: monthly cash flow per company for grouped bar chart."""
    data = get_cross_company_cashflow()
    return jsonify({
        'labels': data['labels'],
        'per_company': data['per_company'],
        'totals': data['totals'],
    })

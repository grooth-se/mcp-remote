from flask import Blueprint, render_template, session, redirect, url_for, jsonify, request
from flask_login import login_required, current_user
from app.extensions import limiter
from app.services.company_service import get_company_summary
from app.models.accounting import Verification
from app.models.audit import AuditLog

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/')
@login_required
def index():
    company_id = session.get('active_company_id')
    summary = None
    recent_verifications = []
    recent_audit = []
    upcoming_deadlines = []
    overdue_deadlines = []
    kpi_data = None
    aging_data = None
    salary_overview = None
    fy_progress = None
    multi_company = None
    recurring_due = 0

    # Seed default favorites on first visit
    from app.services.favorite_service import seed_default_favorites, get_user_favorites
    seed_default_favorites(current_user.id)
    user_favorites = get_user_favorites(current_user.id)

    if company_id:
        # Generate notifications on dashboard load (on-demand)
        from app.services.notification_service import generate_notifications
        generate_notifications(current_user.id, company_id)

        summary = get_company_summary(company_id)

        if summary and summary['active_fiscal_year']:
            fy = summary['active_fiscal_year']
            recent_verifications = Verification.query.filter_by(
                company_id=company_id,
                fiscal_year_id=fy.id,
            ).order_by(Verification.verification_date.desc()).limit(10).all()

            from app.services.dashboard_service import (
                get_kpi_data, get_invoice_aging, get_salary_overview,
                get_fiscal_year_progress,
            )
            kpi_data = get_kpi_data(company_id, fy.id)
            aging_data = get_invoice_aging(company_id)
            salary_overview = get_salary_overview(company_id)
            fy_progress = get_fiscal_year_progress(company_id, fy.id)

        from app.services.dashboard_service import get_recurring_due_count
        recurring_due = get_recurring_due_count(company_id)

        recent_audit = AuditLog.query.filter_by(
            company_id=company_id
        ).order_by(AuditLog.timestamp.desc()).limit(10).all()

        from app.services.tax_service import get_upcoming_deadlines, get_overdue_deadlines
        upcoming_deadlines = get_upcoming_deadlines(company_id, days_ahead=30)
        overdue_deadlines = get_overdue_deadlines(company_id)
    else:
        from app.services.dashboard_service import get_multi_company_overview
        multi_company = get_multi_company_overview()

    return render_template('dashboard/index.html',
                           summary=summary,
                           recent_verifications=recent_verifications,
                           recent_audit=recent_audit,
                           upcoming_deadlines=upcoming_deadlines,
                           overdue_deadlines=overdue_deadlines,
                           kpi_data=kpi_data,
                           aging_data=aging_data,
                           salary_overview=salary_overview,
                           fy_progress=fy_progress,
                           multi_company=multi_company,
                           recurring_due=recurring_due,
                           user_favorites=user_favorites)


@dashboard_bp.route('/switch-company/<int:company_id>')
@login_required
def switch_company(company_id):
    session['active_company_id'] = company_id
    return redirect(url_for('dashboard.index'))


@dashboard_bp.route('/api/revenue-expense-chart')
@login_required
@limiter.limit("60 per minute")
def api_revenue_expense_chart():
    company_id = session.get('active_company_id')
    if not company_id:
        return jsonify({'labels': [], 'revenue': [], 'expenses': []})

    summary = get_company_summary(company_id)
    if not summary or not summary['active_fiscal_year']:
        return jsonify({'labels': [], 'revenue': [], 'expenses': []})

    from app.services.dashboard_service import get_revenue_expense_trend
    data = get_revenue_expense_trend(company_id, summary['active_fiscal_year'].id)
    return jsonify(data)


@dashboard_bp.route('/api/cash-flow-chart')
@login_required
@limiter.limit("60 per minute")
def api_cash_flow_chart():
    company_id = session.get('active_company_id')
    if not company_id:
        return jsonify({'labels': [], 'cash_flow': [], 'balance': []})

    summary = get_company_summary(company_id)
    if not summary or not summary['active_fiscal_year']:
        return jsonify({'labels': [], 'cash_flow': [], 'balance': []})

    from app.services.dashboard_service import get_cash_flow_data
    data = get_cash_flow_data(company_id, summary['active_fiscal_year'].id)
    return jsonify(data)


@dashboard_bp.route('/api/search')
@login_required
@limiter.limit("60 per minute")
def api_search():
    query = request.args.get('q', '').strip()
    company_id = session.get('active_company_id')
    if not company_id or len(query) < 2:
        return jsonify({'results': {}})
    from app.services.search_service import global_search
    results = global_search(company_id, query)
    return jsonify({'results': results})

from flask import Blueprint, render_template, session, redirect, url_for
from flask_login import login_required
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

    if company_id:
        summary = get_company_summary(company_id)

        if summary and summary['active_fiscal_year']:
            recent_verifications = Verification.query.filter_by(
                company_id=company_id,
                fiscal_year_id=summary['active_fiscal_year'].id,
            ).order_by(Verification.verification_date.desc()).limit(10).all()

        recent_audit = AuditLog.query.filter_by(
            company_id=company_id
        ).order_by(AuditLog.timestamp.desc()).limit(10).all()

        from app.services.tax_service import get_upcoming_deadlines, get_overdue_deadlines
        upcoming_deadlines = get_upcoming_deadlines(company_id, days_ahead=30)
        overdue_deadlines = get_overdue_deadlines(company_id)

    return render_template('dashboard/index.html',
                           summary=summary,
                           recent_verifications=recent_verifications,
                           recent_audit=recent_audit,
                           upcoming_deadlines=upcoming_deadlines,
                           overdue_deadlines=overdue_deadlines)


@dashboard_bp.route('/switch-company/<int:company_id>')
@login_required
def switch_company(company_id):
    session['active_company_id'] = company_id
    return redirect(url_for('dashboard.index'))

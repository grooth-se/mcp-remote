"""Main blueprint routes - dashboard."""

from flask import render_template
from . import main_bp
from app.models import FactProjectMonthly, UploadSession


@main_bp.route('/')
def dashboard():
    """Dashboard showing overview and recent activity."""
    # Get recent closing dates
    closing_dates = FactProjectMonthly.get_closing_dates()[:5]

    # Get recent upload sessions
    recent_sessions = UploadSession.query\
        .order_by(UploadSession.created_at.desc())\
        .limit(5).all()

    # Get summary stats for most recent closing date
    stats = None
    if closing_dates:
        latest_date = closing_dates[0]
        projects = FactProjectMonthly.get_by_closing_date(latest_date)
        stats = {
            'closing_date': latest_date,
            'project_count': len(projects),
            'total_accrued': sum(p.accrued_income_cur or 0 for p in projects),
            'total_contingency': sum(p.contingency_cur or 0 for p in projects),
            'total_income': sum(p.total_income_cur or 0 for p in projects),
            'total_cost': sum(p.total_cost_cur or 0 for p in projects),
        }

    return render_template('main/dashboard.html',
                          closing_dates=closing_dates,
                          recent_sessions=recent_sessions,
                          stats=stats)

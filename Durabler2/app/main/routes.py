"""Main routes (dashboard)."""
from flask import render_template
from flask_login import login_required, current_user

from . import main_bp
from app.models import TestRecord


@main_bp.route('/')
@login_required
def dashboard():
    """Main dashboard - equivalent to Tkinter launcher.

    Shows test method buttons and recent activity.
    """
    # Get recent tests for current user
    recent_tests = TestRecord.query.filter_by(operator_id=current_user.id)\
        .order_by(TestRecord.created_at.desc())\
        .limit(10).all()

    # Count tests by status
    draft_count = TestRecord.query.filter_by(status='DRAFT').count()
    analyzed_count = TestRecord.query.filter_by(status='ANALYZED').count()

    return render_template('main/dashboard.html',
                           recent_tests=recent_tests,
                           draft_count=draft_count,
                           analyzed_count=analyzed_count)

"""Audit log admin routes."""
from flask import render_template, request

from . import admin_bp
from app.models import AuditLog, User, ACTION_LABELS, admin_required


@admin_bp.route('/audit')
@admin_required
def audit_log():
    """Browse audit log with filters."""
    page = request.args.get('page', 1, type=int)
    user_filter = request.args.get('user', '')
    action_filter = request.args.get('action', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')

    query = AuditLog.query

    if user_filter:
        query = query.filter(AuditLog.username.ilike(f'%{user_filter}%'))
    if action_filter:
        query = query.filter(AuditLog.action == action_filter)
    if date_from:
        query = query.filter(AuditLog.timestamp >= date_from)
    if date_to:
        query = query.filter(AuditLog.timestamp <= date_to + ' 23:59:59')

    query = query.order_by(AuditLog.timestamp.desc())
    pagination = query.paginate(page=page, per_page=50, error_out=False)

    # Get unique usernames for filter dropdown
    usernames = [u.username for u in User.query.order_by(User.username).all()]

    return render_template(
        'admin/audit_log.html',
        entries=pagination.items,
        pagination=pagination,
        user_filter=user_filter,
        action_filter=action_filter,
        date_from=date_from,
        date_to=date_to,
        action_labels=ACTION_LABELS,
        usernames=usernames,
    )

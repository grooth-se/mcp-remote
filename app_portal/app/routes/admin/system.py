from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import current_user
from app.extensions import db
from app.models.session import UserSession
from app.models.log import AccessLog, AuditLog
from app.utils.decorators import admin_required
from app.utils.logging import log_audit

admin_system_bp = Blueprint('admin_system', __name__)


@admin_system_bp.route('/sessions')
@admin_required
def sessions():
    active_sessions = UserSession.query.filter_by(is_active=True).order_by(
        UserSession.created_at.desc()).all()
    return render_template('admin/system/sessions.html', sessions=active_sessions)


@admin_system_bp.route('/sessions/<int:session_id>/revoke', methods=['POST'])
@admin_required
def revoke_session(session_id):
    session = db.session.get(UserSession, session_id)
    if not session:
        flash('Session not found.', 'danger')
        return redirect(url_for('admin_system.sessions'))

    session.is_active = False
    db.session.commit()
    log_audit(current_user.id, 'revoke_session', 'session', session_id,
              old_value=f'user_id={session.user_id}')
    flash('Session revoked.', 'success')
    return redirect(url_for('admin_system.sessions'))


@admin_system_bp.route('/access-log')
@admin_required
def access_log():
    page = request.args.get('page', 1, type=int)
    action_filter = request.args.get('action', '')
    query = AccessLog.query.order_by(AccessLog.timestamp.desc())
    if action_filter:
        query = query.filter_by(action=action_filter)
    logs = query.paginate(page=page, per_page=50, error_out=False)
    return render_template('admin/system/access_log.html', logs=logs, action_filter=action_filter)


@admin_system_bp.route('/audit-log')
@admin_required
def audit_log():
    page = request.args.get('page', 1, type=int)
    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).paginate(
        page=page, per_page=50, error_out=False)
    return render_template('admin/system/audit_log.html', logs=logs)

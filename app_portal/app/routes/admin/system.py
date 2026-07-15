import csv
from datetime import datetime, timedelta

from flask import (Blueprint, render_template, redirect, url_for, flash, request,
                   jsonify, current_app, Response, stream_with_context)
from flask_login import current_user
from app.extensions import db
from app.models.application import Application
from app.models.session import UserSession
from app.models.log import AccessLog, AuditLog
from app.models.user import User
from app.services import usage_analytics
from app.services.system_metrics import get_host_metrics, get_container_metrics
from app.services.workload_history import get_workload_series
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


@admin_system_bp.route('/status')
@admin_required
def status():
    return render_template('admin/system/status.html',
                           poll_seconds=current_app.config['MONITOR_POLL_SECONDS'])


@admin_system_bp.route('/status/data')
@admin_required
def status_data():
    return jsonify({
        'host': get_host_metrics(),
        'containers': get_container_metrics(),
    })


@admin_system_bp.route('/workload')
@admin_required
def workload():
    return render_template('admin/system/workload.html')


@admin_system_bp.route('/workload/data')
@admin_required
def workload_data():
    range_key = request.args.get('range', '24h')
    scope = request.args.get('scope', 'host')
    metric = request.args.get('metric', 'cpu_pct')
    try:
        source, series = get_workload_series(range_key, scope, metric)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    return jsonify({'range': range_key, 'scope': scope, 'metric': metric,
                    'source': source, 'series': series})


def _parse_usage_filters(args):
    """Extract analytics filters from the query string; bad values ignored."""
    filters = {
        'app_id': args.get('app_id', type=int),
        'user_id': args.get('user_id', type=int),
        'action': args.get('action') if args.get('action') in usage_analytics.USAGE_ACTIONS else None,
        'start': None, 'end': None,
    }
    try:
        if args.get('start'):
            filters['start'] = datetime.strptime(args['start'], '%Y-%m-%d')
        if args.get('end'):
            # inclusive end date -> exclusive upper bound
            filters['end'] = datetime.strptime(args['end'], '%Y-%m-%d') + timedelta(days=1)
    except ValueError:
        pass
    return filters


@admin_system_bp.route('/usage')
@admin_required
def usage():
    filters = _parse_usage_filters(request.args)
    page = request.args.get('page', 1, type=int)
    summary = usage_analytics.per_app_summary(**filters)
    detail = usage_analytics.per_user_app_counts(page=page, **filters)
    apps = Application.query.order_by(Application.app_name).all()
    users = User.query.order_by(User.username).all()
    return render_template('admin/system/usage.html',
                           summary=summary, detail=detail, apps=apps, users=users,
                           actions=usage_analytics.USAGE_ACTIONS)


@admin_system_bp.route('/usage/data')
@admin_required
def usage_data():
    filters = _parse_usage_filters(request.args)
    page = request.args.get('page', 1, type=int)
    summary = usage_analytics.per_app_summary(**filters)
    detail = usage_analytics.per_user_app_counts(page=page, **filters)

    def _iso(ts):
        return ts.isoformat() + 'Z' if ts else None

    for row in summary:
        row['last_used'] = _iso(row['last_used'])
    for item in detail['items']:
        item['last_used'] = _iso(item['last_used'])
    return jsonify({'summary': summary, 'detail': detail})


@admin_system_bp.route('/usage/export.csv')
@admin_required
def usage_export():
    filters = _parse_usage_filters(request.args)
    max_rows = current_app.config['USAGE_EXPORT_MAX_ROWS']

    def generate():
        writer = csv.writer(_CsvEcho())
        yield writer.writerow(['timestamp', 'user', 'action', 'application',
                               'ip_address', 'details'])
        for ts, username, action, app_name, ip, details in \
                usage_analytics.iter_export_rows(max_rows, **filters):
            yield writer.writerow([
                ts.strftime('%Y-%m-%d %H:%M:%S') if ts else '',
                username or '', action or '', app_name or '', ip or '', details or ''])

    return Response(
        stream_with_context(generate()), mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=app_usage.csv'})


class _CsvEcho:
    """File-like object whose write() returns the row, for streaming csv."""
    def write(self, value):
        return value

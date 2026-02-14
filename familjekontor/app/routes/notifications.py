"""Notification center routes (Phase 7B)."""

from flask import Blueprint, render_template, session, redirect, url_for, jsonify, request
from flask_login import login_required, current_user

from app.extensions import csrf
from app.services.notification_service import (
    get_unread_count, get_recent_notifications, get_all_notifications,
    mark_as_read, mark_all_read,
)

notification_bp = Blueprint('notifications', __name__)


@notification_bp.route('/')
@login_required
def index():
    company_id = session.get('active_company_id')
    if not company_id:
        return redirect(url_for('dashboard.index'))

    page = request.args.get('page', 1, type=int)
    filter_type = request.args.get('type')
    filter_read = request.args.get('read')
    read_val = None
    if filter_read == '0':
        read_val = False
    elif filter_read == '1':
        read_val = True

    pagination = get_all_notifications(
        current_user.id, company_id, page=page,
        filter_type=filter_type, filter_read=read_val,
    )
    return render_template('notifications/index.html',
                           pagination=pagination,
                           filter_type=filter_type,
                           filter_read=filter_read)


@notification_bp.route('/<int:notification_id>/read', methods=['POST'])
@login_required
def mark_read(notification_id):
    ok = mark_as_read(notification_id, current_user.id)
    if request.is_json:
        return jsonify({'ok': ok})
    return redirect(url_for('notifications.index'))


@notification_bp.route('/mark-all-read', methods=['POST'])
@login_required
def mark_all():
    company_id = session.get('active_company_id')
    if not company_id:
        return jsonify({'ok': False}), 400
    count = mark_all_read(current_user.id, company_id)
    if request.is_json:
        return jsonify({'ok': True, 'count': count})
    return redirect(url_for('notifications.index'))


# JSON API endpoints — CSRF-exempt for AJAX
@notification_bp.route('/api/count')
@login_required
def api_count():
    company_id = session.get('active_company_id')
    if not company_id:
        return jsonify({'count': 0})
    return jsonify({'count': get_unread_count(current_user.id, company_id)})


@notification_bp.route('/api/recent')
@login_required
def api_recent():
    company_id = session.get('active_company_id')
    if not company_id:
        return jsonify({'notifications': []})
    notifs = get_recent_notifications(current_user.id, company_id)
    return jsonify({
        'notifications': [
            {
                'id': n.id,
                'title': n.title,
                'message': n.message or '',
                'link': n.link or '',
                'icon': n.icon or 'bi-bell',
                'read': n.read,
                'type': n.notification_type,
                'created_at': n.created_at.strftime('%Y-%m-%d %H:%M') if n.created_at else '',
            }
            for n in notifs
        ]
    })

from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import current_user
from app.extensions import db
from app.models.user import User
from app.models.application import Application
from app.models.permission import UserPermission
from app.utils.decorators import admin_required
from app.utils.logging import log_audit

admin_permissions_bp = Blueprint('admin_permissions', __name__)


@admin_permissions_bp.route('/')
@admin_required
def matrix():
    users = User.query.order_by(User.username).all()
    apps = Application.query.order_by(Application.display_order).all()

    # Build permission lookup: {(user_id, app_id): True}
    perms = {}
    for p in UserPermission.query.all():
        perms[(p.user_id, p.app_id)] = True

    return render_template('admin/permissions/matrix.html',
                           users=users, apps=apps, perms=perms)


@admin_permissions_bp.route('/update', methods=['POST'])
@admin_required
def update():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data'}), 400

    user_id = data.get('user_id')
    app_id = data.get('app_id')
    granted = data.get('granted')

    if not user_id or not app_id:
        return jsonify({'error': 'Missing user_id or app_id'}), 400

    user = db.session.get(User, user_id)
    app = db.session.get(Application, app_id)
    if not user or not app:
        return jsonify({'error': 'User or app not found'}), 404

    existing = UserPermission.query.filter_by(user_id=user_id, app_id=app_id).first()

    if granted and not existing:
        perm = UserPermission(user_id=user_id, app_id=app_id, granted_by=current_user.id)
        db.session.add(perm)
        db.session.commit()
        log_audit(current_user.id, 'grant_permission', 'permission', perm.id,
                  new_value=f'{user.username} -> {app.app_code}')
        return jsonify({'status': 'granted'})
    elif not granted and existing:
        log_audit(current_user.id, 'revoke_permission', 'permission', existing.id,
                  old_value=f'{user.username} -> {app.app_code}')
        db.session.delete(existing)
        db.session.commit()
        return jsonify({'status': 'revoked'})

    return jsonify({'status': 'unchanged'})

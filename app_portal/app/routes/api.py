from flask import Blueprint, request, jsonify
from app.services.token_service import validate_token
from app.models.user import User
from app.models.permission import UserPermission
from app.models.application import Application
from app.extensions import db

api_bp = Blueprint('api', __name__)


@api_bp.route('/validate-token', methods=['POST'])
def validate_token_endpoint():
    data = request.get_json()
    if not data or 'token' not in data:
        return jsonify({'valid': False, 'error': 'Missing token'}), 400

    token = data['token']
    app_code = data.get('app_code')

    payload = validate_token(token)
    if not payload:
        return jsonify({'valid': False, 'error': 'Invalid or expired token'}), 401

    user = db.session.get(User, payload['user_id'])
    if not user or not user.is_active:
        return jsonify({'valid': False, 'error': 'User not found or inactive'}), 401

    # Check app permission if app_code provided
    if app_code and not user.has_app_permission(app_code):
        return jsonify({'valid': False, 'error': 'Access denied for this application'}), 403

    # Get user's permitted app codes
    if user.is_admin:
        permitted = [a.app_code for a in Application.query.filter_by(is_active=True).all()]
    else:
        perms = UserPermission.query.filter_by(user_id=user.id).all()
        app_ids = [p.app_id for p in perms]
        permitted = [a.app_code for a in Application.query.filter(
            Application.id.in_(app_ids), Application.is_active == True  # noqa: E712
        ).all()]

    return jsonify({
        'valid': True,
        'user': {
            'id': user.id,
            'username': user.username,
            'display_name': user.display_name,
            'is_admin': user.is_admin,
        },
        'permissions': permitted,
    })

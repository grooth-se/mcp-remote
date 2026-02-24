"""Tests for token validation API."""
import json
from app.services.token_service import generate_token
from app.models.permission import UserPermission


def test_validate_token_success(client, app, admin_user):
    with app.app_context():
        token = generate_token(admin_user.id, 8)

    resp = client.post('/api/validate-token',
        data=json.dumps({'token': token}),
        content_type='application/json')
    data = resp.get_json()
    assert data['valid'] is True
    assert data['user']['username'] == 'admin1'
    assert data['user']['is_admin'] is True


def test_validate_token_with_app_code(client, app, db, normal_user, sample_app):
    perm = UserPermission(user_id=normal_user.id, app_id=sample_app.id)
    db.session.add(perm)
    db.session.commit()

    with app.app_context():
        token = generate_token(normal_user.id, 8)

    resp = client.post('/api/validate-token',
        data=json.dumps({'token': token, 'app_code': 'testapp'}),
        content_type='application/json')
    data = resp.get_json()
    assert data['valid'] is True
    assert 'testapp' in data['permissions']


def test_validate_token_no_permission(client, app, db, normal_user, sample_app):
    with app.app_context():
        token = generate_token(normal_user.id, 8)

    resp = client.post('/api/validate-token',
        data=json.dumps({'token': token, 'app_code': 'testapp'}),
        content_type='application/json')
    assert resp.status_code == 403
    data = resp.get_json()
    assert data['valid'] is False


def test_validate_token_invalid(client, app):
    resp = client.post('/api/validate-token',
        data=json.dumps({'token': 'invalid.token.here'}),
        content_type='application/json')
    assert resp.status_code == 401
    data = resp.get_json()
    assert data['valid'] is False


def test_validate_token_missing(client, app):
    resp = client.post('/api/validate-token',
        data=json.dumps({}),
        content_type='application/json')
    assert resp.status_code == 400


def test_validate_token_inactive_user(client, app, db, normal_user):
    with app.app_context():
        token = generate_token(normal_user.id, 8)

    normal_user.is_active_user = False
    db.session.commit()

    resp = client.post('/api/validate-token',
        data=json.dumps({'token': token}),
        content_type='application/json')
    assert resp.status_code == 401
    data = resp.get_json()
    assert data['valid'] is False

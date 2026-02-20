"""Tests for per-app role management."""
import json
from app.models.application import Application
from app.models.permission import UserPermission
from app.services.token_service import generate_token

DURABLER_ROLES = {
    'operator': 'Operator',
    'engineer': 'Test Engineer',
    'approver': 'Approver',
    'admin': 'Administrator',
}


# --- Application model helpers ---

def test_get_available_roles_empty(app, sample_app):
    assert sample_app.get_available_roles() == {}


def test_get_available_roles_with_dict(app, db):
    application = Application(
        app_code='roleapp', app_name='Role App',
        internal_url='http://localhost:9000',
        available_roles=json.dumps(DURABLER_ROLES),
        default_role='operator',
    )
    db.session.add(application)
    db.session.commit()
    roles = application.get_available_roles()
    assert roles == DURABLER_ROLES
    assert application.default_role == 'operator'


def test_get_available_roles_legacy_list(app, db):
    """Legacy list format is converted to {value: value} dict."""
    application = Application(
        app_code='legacyapp', app_name='Legacy App',
        internal_url='http://localhost:9000',
        available_roles=json.dumps(['admin', 'viewer']),
    )
    db.session.add(application)
    db.session.commit()
    assert application.get_available_roles() == {'admin': 'admin', 'viewer': 'viewer'}


def test_set_available_roles(app, sample_app, db):
    sample_app.set_available_roles({'admin': 'Admin', 'user': 'User'})
    db.session.commit()
    assert sample_app.get_available_roles() == {'admin': 'Admin', 'user': 'User'}


def test_set_available_roles_clears(app, sample_app, db):
    sample_app.set_available_roles({'admin': 'Admin'})
    db.session.commit()
    sample_app.set_available_roles(None)
    db.session.commit()
    assert sample_app.get_available_roles() == {}


def test_get_available_roles_invalid_json(app, sample_app, db):
    sample_app.available_roles = 'not-json'
    db.session.commit()
    assert sample_app.get_available_roles() == {}


# --- UserPermission role column ---

def test_permission_with_role(app, db, normal_user, sample_app):
    perm = UserPermission(user_id=normal_user.id, app_id=sample_app.id, role='engineer')
    db.session.add(perm)
    db.session.commit()
    assert perm.role == 'engineer'


def test_permission_role_nullable(app, db, normal_user, sample_app):
    perm = UserPermission(user_id=normal_user.id, app_id=sample_app.id)
    db.session.add(perm)
    db.session.commit()
    assert perm.role is None


# --- Validate token API returns role ---

def test_validate_token_returns_role_for_user(client, app, db, normal_user):
    """User with explicit role on app gets that role in response."""
    application = Application(
        app_code='durabler2', app_name='Durabler2',
        internal_url='http://localhost:5005',
        available_roles=json.dumps(DURABLER_ROLES),
        default_role='operator',
    )
    db.session.add(application)
    db.session.flush()
    perm = UserPermission(user_id=normal_user.id, app_id=application.id, role='engineer')
    db.session.add(perm)
    db.session.commit()

    with app.app_context():
        token = generate_token(normal_user.id, 8)

    resp = client.post('/api/validate-token',
        data=json.dumps({'token': token, 'app_code': 'durabler2'}),
        content_type='application/json')
    data = resp.get_json()
    assert data['valid'] is True
    assert data['user']['role'] == 'engineer'


def test_validate_token_returns_default_role(client, app, db, normal_user):
    """User without explicit role gets app's default_role."""
    application = Application(
        app_code='durabler2', app_name='Durabler2',
        internal_url='http://localhost:5005',
        available_roles=json.dumps(DURABLER_ROLES),
        default_role='operator',
    )
    db.session.add(application)
    db.session.flush()
    perm = UserPermission(user_id=normal_user.id, app_id=application.id)
    db.session.add(perm)
    db.session.commit()

    with app.app_context():
        token = generate_token(normal_user.id, 8)

    resp = client.post('/api/validate-token',
        data=json.dumps({'token': token, 'app_code': 'durabler2'}),
        content_type='application/json')
    data = resp.get_json()
    assert data['valid'] is True
    assert data['user']['role'] == 'operator'


def test_validate_token_admin_gets_admin_role(client, app, db, admin_user):
    """Admin users get role='admin' for apps with roles."""
    application = Application(
        app_code='durabler2', app_name='Durabler2',
        internal_url='http://localhost:5005',
        available_roles=json.dumps(DURABLER_ROLES),
        default_role='operator',
    )
    db.session.add(application)
    db.session.commit()

    with app.app_context():
        token = generate_token(admin_user.id, 8)

    resp = client.post('/api/validate-token',
        data=json.dumps({'token': token, 'app_code': 'durabler2'}),
        content_type='application/json')
    data = resp.get_json()
    assert data['valid'] is True
    assert data['user']['role'] == 'admin'


def test_validate_token_no_role_for_app_without_roles(client, app, db, normal_user, sample_app):
    """Apps without available_roles return role=None."""
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
    assert data['user']['role'] is None


def test_validate_token_no_role_without_app_code(client, app, admin_user):
    """No role when app_code not provided."""
    with app.app_context():
        token = generate_token(admin_user.id, 8)

    resp = client.post('/api/validate-token',
        data=json.dumps({'token': token}),
        content_type='application/json')
    data = resp.get_json()
    assert data['valid'] is True
    assert data['user']['role'] is None


# --- Permission toggle with role ---

def test_grant_permission_with_role(logged_in_client, db, normal_user):
    application = Application(
        app_code='durabler2', app_name='Durabler2',
        internal_url='http://localhost:5005',
        available_roles=json.dumps(DURABLER_ROLES),
        default_role='operator',
    )
    db.session.add(application)
    db.session.commit()

    resp = logged_in_client.post('/admin/permissions/update',
        data=json.dumps({
            'user_id': normal_user.id,
            'app_id': application.id,
            'granted': True,
            'role': 'engineer',
        }),
        content_type='application/json')
    data = resp.get_json()
    assert data['status'] == 'granted'
    assert data['role'] == 'engineer'

    perm = UserPermission.query.filter_by(user_id=normal_user.id, app_id=application.id).first()
    assert perm.role == 'engineer'


def test_grant_permission_uses_default_role(logged_in_client, db, normal_user):
    application = Application(
        app_code='durabler2', app_name='Durabler2',
        internal_url='http://localhost:5005',
        available_roles=json.dumps(DURABLER_ROLES),
        default_role='operator',
    )
    db.session.add(application)
    db.session.commit()

    resp = logged_in_client.post('/admin/permissions/update',
        data=json.dumps({
            'user_id': normal_user.id,
            'app_id': application.id,
            'granted': True,
        }),
        content_type='application/json')
    data = resp.get_json()
    assert data['status'] == 'granted'
    assert data['role'] == 'operator'


# --- Set role endpoint ---

def test_set_role(logged_in_client, db, normal_user):
    application = Application(
        app_code='durabler2', app_name='Durabler2',
        internal_url='http://localhost:5005',
        available_roles=json.dumps(DURABLER_ROLES),
        default_role='operator',
    )
    db.session.add(application)
    db.session.flush()
    perm = UserPermission(user_id=normal_user.id, app_id=application.id, role='operator')
    db.session.add(perm)
    db.session.commit()

    resp = logged_in_client.post('/admin/permissions/set-role',
        data=json.dumps({
            'user_id': normal_user.id,
            'app_id': application.id,
            'role': 'approver',
        }),
        content_type='application/json')
    data = resp.get_json()
    assert data['status'] == 'updated'
    assert data['role'] == 'approver'

    perm = UserPermission.query.filter_by(user_id=normal_user.id, app_id=application.id).first()
    assert perm.role == 'approver'


def test_set_role_invalid_role(logged_in_client, db, normal_user):
    application = Application(
        app_code='durabler2', app_name='Durabler2',
        internal_url='http://localhost:5005',
        available_roles=json.dumps(DURABLER_ROLES),
        default_role='operator',
    )
    db.session.add(application)
    db.session.flush()
    perm = UserPermission(user_id=normal_user.id, app_id=application.id, role='operator')
    db.session.add(perm)
    db.session.commit()

    resp = logged_in_client.post('/admin/permissions/set-role',
        data=json.dumps({
            'user_id': normal_user.id,
            'app_id': application.id,
            'role': 'hacker',
        }),
        content_type='application/json')
    assert resp.status_code == 400


def test_set_role_no_permission(logged_in_client, db, normal_user, sample_app):
    resp = logged_in_client.post('/admin/permissions/set-role',
        data=json.dumps({
            'user_id': normal_user.id,
            'app_id': sample_app.id,
            'role': 'admin',
        }),
        content_type='application/json')
    assert resp.status_code == 404


# --- Permission matrix route ---

def test_permission_matrix_shows_roles(logged_in_client, db, normal_user):
    application = Application(
        app_code='durabler2', app_name='Durabler2',
        internal_url='http://localhost:5005',
        available_roles=json.dumps(DURABLER_ROLES),
        default_role='operator',
    )
    db.session.add(application)
    db.session.flush()
    perm = UserPermission(user_id=normal_user.id, app_id=application.id, role='engineer')
    db.session.add(perm)
    db.session.commit()

    resp = logged_in_client.get('/admin/permissions/')
    assert resp.status_code == 200
    assert b'role-dropdown' in resp.data
    assert b'Test Engineer' in resp.data

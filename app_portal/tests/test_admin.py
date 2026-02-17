"""Tests for admin routes."""
import json


# --- User Management ---

def test_admin_users_list(logged_in_client, admin_user):
    resp = logged_in_client.get('/admin/users/')
    assert resp.status_code == 200
    assert b'admin' in resp.data


def test_admin_users_forbidden_for_normal_user(user_logged_in_client):
    resp = user_logged_in_client.get('/admin/users/')
    assert resp.status_code == 403


def test_create_user(logged_in_client):
    resp = logged_in_client.post('/admin/users/create', data={
        'username': 'newuser',
        'display_name': 'New User',
        'email': 'new@test.com',
        'password': 'newpass12',
        'is_admin': False,
    }, follow_redirects=True)
    assert b'newuser' in resp.data
    assert b'created' in resp.data


def test_create_user_duplicate(logged_in_client, normal_user):
    resp = logged_in_client.post('/admin/users/create', data={
        'username': 'testuser',
        'display_name': 'Dup',
        'password': 'pass1234',
    }, follow_redirects=True)
    assert b'already exists' in resp.data


def test_edit_user(logged_in_client, normal_user):
    resp = logged_in_client.post(f'/admin/users/{normal_user.id}/edit', data={
        'display_name': 'Updated Name',
        'email': 'updated@test.com',
    }, follow_redirects=True)
    assert b'User updated' in resp.data


def test_reset_password(logged_in_client, normal_user):
    resp = logged_in_client.post(f'/admin/users/{normal_user.id}/reset-password', data={
        'new_password': 'resetpass1',
    }, follow_redirects=True)
    assert b'Password reset' in resp.data


def test_toggle_active(logged_in_client, normal_user):
    resp = logged_in_client.post(f'/admin/users/{normal_user.id}/toggle-active',
                                  follow_redirects=True)
    assert b'deactivated' in resp.data


def test_toggle_active_self(logged_in_client, admin_user):
    resp = logged_in_client.post(f'/admin/users/{admin_user.id}/toggle-active',
                                  follow_redirects=True)
    assert b'cannot deactivate yourself' in resp.data


def test_toggle_admin(logged_in_client, normal_user):
    resp = logged_in_client.post(f'/admin/users/{normal_user.id}/toggle-admin',
                                  follow_redirects=True)
    assert b'granted' in resp.data


def test_delete_user(logged_in_client, normal_user):
    resp = logged_in_client.post(f'/admin/users/{normal_user.id}/delete',
                                  follow_redirects=True)
    assert b'deleted' in resp.data


def test_delete_self(logged_in_client, admin_user):
    resp = logged_in_client.post(f'/admin/users/{admin_user.id}/delete',
                                  follow_redirects=True)
    assert b'cannot delete yourself' in resp.data


# --- App Management ---

def test_admin_apps_list(logged_in_client, sample_apps):
    resp = logged_in_client.get('/admin/apps/')
    assert resp.status_code == 200
    assert b'Accrued Income' in resp.data


def test_create_app(logged_in_client):
    resp = logged_in_client.post('/admin/apps/create', data={
        'app_code': 'newapp',
        'app_name': 'New App',
        'description': 'A new application',
        'internal_url': 'http://localhost:9000',
        'icon': 'bi-star',
        'display_order': 10,
    }, follow_redirects=True)
    assert b'New App' in resp.data
    assert b'registered' in resp.data


def test_edit_app(logged_in_client, sample_app):
    resp = logged_in_client.post(f'/admin/apps/{sample_app.id}/edit', data={
        'app_code': 'testapp',
        'app_name': 'Updated App',
        'internal_url': 'http://localhost:9999',
        'display_order': 5,
    }, follow_redirects=True)
    assert b'Application updated' in resp.data


def test_toggle_app_active(logged_in_client, sample_app):
    resp = logged_in_client.post(f'/admin/apps/{sample_app.id}/toggle-active',
                                  follow_redirects=True)
    assert b'disabled' in resp.data


# --- Permissions ---

def test_permission_matrix(logged_in_client, normal_user, sample_apps):
    resp = logged_in_client.get('/admin/permissions/')
    assert resp.status_code == 200
    assert b'testuser' in resp.data


def test_grant_permission(logged_in_client, normal_user, sample_app):
    resp = logged_in_client.post('/admin/permissions/update',
        data=json.dumps({
            'user_id': normal_user.id,
            'app_id': sample_app.id,
            'granted': True,
        }),
        content_type='application/json')
    data = resp.get_json()
    assert data['status'] == 'granted'


def test_revoke_permission(logged_in_client, db, normal_user, sample_app):
    from app.models.permission import UserPermission
    perm = UserPermission(user_id=normal_user.id, app_id=sample_app.id)
    db.session.add(perm)
    db.session.commit()

    resp = logged_in_client.post('/admin/permissions/update',
        data=json.dumps({
            'user_id': normal_user.id,
            'app_id': sample_app.id,
            'granted': False,
        }),
        content_type='application/json')
    data = resp.get_json()
    assert data['status'] == 'revoked'


# --- System ---

def test_sessions_page(logged_in_client):
    resp = logged_in_client.get('/admin/system/sessions')
    assert resp.status_code == 200


def test_access_log_page(logged_in_client, admin_user):
    resp = logged_in_client.get('/admin/system/access-log')
    assert resp.status_code == 200


def test_audit_log_page(logged_in_client):
    resp = logged_in_client.get('/admin/system/audit-log')
    assert resp.status_code == 200

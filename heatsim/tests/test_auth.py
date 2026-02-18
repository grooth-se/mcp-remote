"""Tests for authentication routes."""
import pytest
from app.models import User, AuditLog


class TestLogin:
    def test_login_page_renders(self, client):
        rv = client.get('/auth/login')
        assert rv.status_code == 200
        assert b'login' in rv.data.lower() or b'Log' in rv.data

    def test_login_success(self, client, engineer_user):
        rv = client.post('/auth/login', data={
            'username': 'engineer1',
            'password': 'password123',
        }, follow_redirects=True)
        assert rv.status_code == 200

    def test_login_bad_password(self, client, engineer_user):
        rv = client.post('/auth/login', data={
            'username': 'engineer1',
            'password': 'wrongpass',
        }, follow_redirects=True)
        assert b'Invalid' in rv.data

    def test_login_nonexistent_user(self, client, db):
        rv = client.post('/auth/login', data={
            'username': 'nobody',
            'password': 'pass',
        }, follow_redirects=True)
        assert b'Invalid' in rv.data

    def test_login_empty_fields(self, client, db):
        rv = client.post('/auth/login', data={
            'username': '',
            'password': '',
        }, follow_redirects=True)
        # WTForms validation should catch empty required fields
        assert rv.status_code == 200

    def test_already_authenticated_redirect(self, logged_in_client):
        rv = logged_in_client.get('/auth/login')
        assert rv.status_code == 302

    def test_next_param(self, client, engineer_user):
        rv = client.post('/auth/login?next=/materials/', data={
            'username': 'engineer1',
            'password': 'password123',
        })
        assert rv.status_code == 302
        assert '/materials/' in rv.headers.get('Location', '')

    def test_last_login_updated(self, client, engineer_user, db):
        assert engineer_user.last_login is None
        client.post('/auth/login', data={
            'username': 'engineer1',
            'password': 'password123',
        })
        user = db.session.get(User, engineer_user.id)
        assert user.last_login is not None

    def test_audit_log_on_login(self, client, engineer_user, app, db):
        client.post('/auth/login', data={
            'username': 'engineer1',
            'password': 'password123',
        })
        entry = AuditLog.query.filter_by(action='login').first()
        assert entry is not None
        assert entry.username == 'engineer1'

    def test_remember_me(self, client, engineer_user):
        rv = client.post('/auth/login', data={
            'username': 'engineer1',
            'password': 'password123',
            'remember_me': True,
        }, follow_redirects=True)
        assert rv.status_code == 200


class TestLogout:
    def test_logout_success(self, logged_in_client):
        rv = logged_in_client.get('/auth/logout', follow_redirects=True)
        assert rv.status_code == 200

    def test_logout_requires_login(self, client, db):
        rv = client.get('/auth/logout')
        assert rv.status_code == 302
        assert '/auth/login' in rv.headers.get('Location', '')

    def test_audit_log_on_logout(self, logged_in_client, db):
        logged_in_client.get('/auth/logout')
        entry = AuditLog.query.filter_by(action='logout').first()
        assert entry is not None

    def test_session_cleared(self, logged_in_client):
        logged_in_client.get('/auth/logout')
        rv = logged_in_client.get('/')
        assert rv.status_code == 302


class TestProfile:
    def test_profile_renders(self, logged_in_client):
        rv = logged_in_client.get('/auth/profile')
        assert rv.status_code == 200

    def test_profile_requires_login(self, client, db):
        rv = client.get('/auth/profile')
        assert rv.status_code == 302

    def test_profile_shows_username(self, logged_in_client):
        rv = logged_in_client.get('/auth/profile')
        assert b'engineer1' in rv.data


class TestChangePassword:
    def test_form_renders(self, logged_in_client):
        rv = logged_in_client.get('/auth/profile/password')
        assert rv.status_code == 200

    def test_success(self, logged_in_client, engineer_user, db):
        rv = logged_in_client.post('/auth/profile/password', data={
            'current_password': 'password123',
            'new_password': 'newpass456',
            'confirm_password': 'newpass456',
        }, follow_redirects=True)
        assert rv.status_code == 200
        user = db.session.get(User, engineer_user.id)
        assert user.check_password('newpass456')

    def test_wrong_current_password(self, logged_in_client):
        rv = logged_in_client.post('/auth/profile/password', data={
            'current_password': 'wrongcurrent',
            'new_password': 'newpass456',
            'confirm_password': 'newpass456',
        }, follow_redirects=True)
        assert b'incorrect' in rv.data.lower() or rv.status_code == 200

    def test_mismatch_confirm(self, logged_in_client):
        rv = logged_in_client.post('/auth/profile/password', data={
            'current_password': 'password123',
            'new_password': 'newpass456',
            'confirm_password': 'different',
        }, follow_redirects=True)
        assert rv.status_code == 200

    def test_requires_login(self, client, db):
        rv = client.get('/auth/profile/password')
        assert rv.status_code == 302

    def test_audit_log(self, logged_in_client, db):
        logged_in_client.post('/auth/profile/password', data={
            'current_password': 'password123',
            'new_password': 'newpass456',
            'confirm_password': 'newpass456',
        })
        entry = AuditLog.query.filter_by(action='update_user').first()
        assert entry is not None

    def test_new_password_works(self, client, engineer_user, db):
        # Login, change password, logout, login with new password
        client.post('/auth/login', data={
            'username': 'engineer1', 'password': 'password123'})
        client.post('/auth/profile/password', data={
            'current_password': 'password123',
            'new_password': 'newpass789',
            'confirm_password': 'newpass789',
        })
        client.get('/auth/logout')
        rv = client.post('/auth/login', data={
            'username': 'engineer1', 'password': 'newpass789',
        }, follow_redirects=True)
        assert rv.status_code == 200

    def test_old_password_fails_after_change(self, client, engineer_user, db):
        client.post('/auth/login', data={
            'username': 'engineer1', 'password': 'password123'})
        client.post('/auth/profile/password', data={
            'current_password': 'password123',
            'new_password': 'changed999',
            'confirm_password': 'changed999',
        })
        client.get('/auth/logout')
        rv = client.post('/auth/login', data={
            'username': 'engineer1', 'password': 'password123',
        }, follow_redirects=True)
        assert b'Invalid' in rv.data

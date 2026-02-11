"""Tests for infrastructure and production hardening (Phase 5B)."""
import os

import pytest

from app import create_app
from app.models.audit import AuditLog
from config import ProductionConfig


class TestErrorPages:
    def test_404_page(self, logged_in_client):
        response = logged_in_client.get('/nonexistent-page-xyz')
        assert response.status_code == 404
        assert 'Sidan hittades inte' in response.data.decode()

    def test_500_handler_exists(self, app):
        handler_map = app.error_handler_spec.get(None, {})
        assert 500 in handler_map


class TestSecurityHeaders:
    def test_x_frame_options(self, logged_in_client):
        response = logged_in_client.get('/login')
        assert response.headers.get('X-Frame-Options') == 'DENY'

    def test_x_content_type_options(self, logged_in_client):
        response = logged_in_client.get('/login')
        assert response.headers.get('X-Content-Type-Options') == 'nosniff'

    def test_referrer_policy(self, logged_in_client):
        response = logged_in_client.get('/login')
        assert response.headers.get('Referrer-Policy') == 'strict-origin-when-cross-origin'

    def test_permissions_policy(self, logged_in_client):
        response = logged_in_client.get('/login')
        assert 'camera=()' in response.headers.get('Permissions-Policy', '')


class TestSessionConfig:
    def test_cookie_httponly(self, app):
        assert app.config['SESSION_COOKIE_HTTPONLY'] is True

    def test_cookie_samesite(self, app):
        assert app.config['SESSION_COOKIE_SAMESITE'] == 'Lax'

    def test_session_lifetime(self, app):
        assert app.config['PERMANENT_SESSION_LIFETIME'] == 3600


class TestOpenRedirect:
    def test_open_redirect_blocked(self, db, client):
        from app.models.user import User
        user = User(username='redir_test', email='redir@test.com', role='user')
        user.set_password('Testpass1')
        db.session.add(user)
        db.session.commit()

        response = client.post('/login?next=https://evil.com', data={
            'username': 'redir_test',
            'password': 'Testpass1',
        })
        assert response.status_code == 302
        assert 'evil.com' not in response.headers.get('Location', '')

    def test_open_redirect_local_allowed(self, db, client):
        from app.models.user import User
        user = User(username='redir_local', email='redir_local@test.com', role='user')
        user.set_password('Testpass1')
        db.session.add(user)
        db.session.commit()

        response = client.post('/login?next=/companies/', data={
            'username': 'redir_local',
            'password': 'Testpass1',
        })
        assert response.status_code == 302
        assert '/companies/' in response.headers.get('Location', '')


class TestPasswordPolicy:
    def _validate_password(self, app, password):
        from app.forms.admin import UserForm
        from werkzeug.datastructures import MultiDict
        with app.test_request_context():
            form = UserForm(formdata=MultiDict({
                'username': 'test', 'email': 'a@b.com',
                'password': password, 'role': 'user',
            }))
            form.password.validate(form)
            return form.password.errors

    def test_password_too_short(self, app):
        errors = self._validate_password(app, 'Short1')
        assert len(errors) > 0

    def test_password_digits_only(self, app):
        errors = self._validate_password(app, '12345678')
        assert len(errors) > 0

    def test_password_letters_only(self, app):
        errors = self._validate_password(app, 'abcdefgh')
        assert len(errors) > 0

    def test_password_valid(self, app):
        errors = self._validate_password(app, 'Passw0rd')
        assert len(errors) == 0


class TestLoginAudit:
    def test_login_audit_success(self, db, client):
        from app.models.user import User
        user = User(username='audit_ok', email='audit_ok@test.com', role='user')
        user.set_password('Testpass1')
        db.session.add(user)
        db.session.commit()

        client.post('/login', data={
            'username': 'audit_ok', 'password': 'Testpass1',
        })
        log = AuditLog.query.filter_by(action='login', user_id=user.id).first()
        assert log is not None
        assert log.entity_type == 'user'

    def test_login_audit_failure(self, db, client):
        client.post('/login', data={
            'username': 'nonexistent', 'password': 'wrong',
        })
        log = AuditLog.query.filter_by(action='login_failed').first()
        assert log is not None
        assert log.user_id is None
        assert log.new_values['username'] == 'nonexistent'


class TestProductionConfig:
    def test_production_rejects_default_secret_key(self):
        env_backup = os.environ.pop('SECRET_KEY', None)
        try:
            with pytest.raises(RuntimeError, match='SECRET_KEY'):
                create_app('production')
        finally:
            if env_backup is not None:
                os.environ['SECRET_KEY'] = env_backup

    def test_production_secure_cookie(self):
        assert ProductionConfig.SESSION_COOKIE_SECURE is True


class TestRunConfig:
    def test_run_binds_localhost(self):
        with open(os.path.join(os.path.dirname(__file__), '..', 'run.py')) as f:
            content = f.read()
        assert "host='127.0.0.1'" in content
        assert "host='0.0.0.0'" not in content
        assert 'debug=True' not in content.split('if __name__')[1]

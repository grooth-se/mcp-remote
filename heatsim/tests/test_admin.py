"""Tests for admin routes."""
import pytest
from app.models import User, AuditLog, SystemSetting, ROLE_ADMIN, ROLE_ENGINEER


class TestAdminDashboard:
    def test_renders(self, admin_client):
        rv = admin_client.get('/admin/')
        assert rv.status_code == 200

    def test_requires_admin(self, logged_in_client):
        rv = logged_in_client.get('/admin/')
        assert rv.status_code == 302

    def test_requires_login(self, client, db):
        rv = client.get('/admin/')
        assert rv.status_code == 302

    def test_shows_stats(self, admin_client):
        rv = admin_client.get('/admin/')
        assert rv.status_code == 200


class TestUserList:
    def test_renders(self, admin_client):
        rv = admin_client.get('/admin/users')
        assert rv.status_code == 200

    def test_shows_users(self, admin_client, admin_user):
        rv = admin_client.get('/admin/users')
        assert b'admin1' in rv.data

    def test_search_filter(self, admin_client, admin_user):
        rv = admin_client.get('/admin/users?q=admin')
        assert rv.status_code == 200

    def test_role_filter(self, admin_client, admin_user):
        rv = admin_client.get('/admin/users?role=admin')
        assert rv.status_code == 200

    def test_requires_admin(self, logged_in_client):
        rv = logged_in_client.get('/admin/users')
        assert rv.status_code == 302


class TestCreateUser:
    def test_form_renders(self, admin_client):
        rv = admin_client.get('/admin/users/new')
        assert rv.status_code == 200

    def test_success(self, admin_client, db):
        rv = admin_client.post('/admin/users/new', data={
            'username': 'newuser',
            'password': 'password123',
            'confirm_password': 'password123',
            'role': ROLE_ENGINEER,
        }, follow_redirects=True)
        assert rv.status_code == 200
        assert User.query.filter_by(username='newuser').first() is not None

    def test_duplicate_username(self, admin_client, admin_user, db):
        rv = admin_client.post('/admin/users/new', data={
            'username': 'admin1',
            'password': 'pass123456',
            'confirm_password': 'pass123456',
            'role': ROLE_ENGINEER,
        }, follow_redirects=True)
        assert rv.status_code == 200

    def test_password_mismatch(self, admin_client, db):
        rv = admin_client.post('/admin/users/new', data={
            'username': 'mismatch',
            'password': 'password123',
            'confirm_password': 'different',
            'role': ROLE_ENGINEER,
        }, follow_redirects=True)
        assert rv.status_code == 200
        assert User.query.filter_by(username='mismatch').first() is None

    def test_audit_log(self, admin_client, db):
        admin_client.post('/admin/users/new', data={
            'username': 'audited',
            'password': 'password123',
            'confirm_password': 'password123',
            'role': ROLE_ENGINEER,
        })
        entry = AuditLog.query.filter_by(action='create_user').first()
        assert entry is not None

    def test_requires_admin(self, logged_in_client):
        rv = logged_in_client.get('/admin/users/new')
        assert rv.status_code == 302


class TestEditUser:
    def test_form_renders(self, admin_client, engineer_user):
        rv = admin_client.get(f'/admin/users/{engineer_user.id}/edit')
        assert rv.status_code == 200

    def test_change_role(self, admin_client, engineer_user, db):
        rv = admin_client.post(f'/admin/users/{engineer_user.id}/edit', data={
            'role': ROLE_ADMIN,
        }, follow_redirects=True)
        assert rv.status_code == 200
        user = db.session.get(User, engineer_user.id)
        assert user.role == ROLE_ADMIN

    def test_reset_password(self, admin_client, engineer_user, db):
        rv = admin_client.post(f'/admin/users/{engineer_user.id}/edit', data={
            'role': ROLE_ENGINEER,
            'new_password': 'resetpass',
            'confirm_password': 'resetpass',
        }, follow_redirects=True)
        assert rv.status_code == 200
        user = db.session.get(User, engineer_user.id)
        assert user.check_password('resetpass')

    def test_no_password_keeps_old(self, admin_client, engineer_user, db):
        admin_client.post(f'/admin/users/{engineer_user.id}/edit', data={
            'role': ROLE_ENGINEER,
        })
        user = db.session.get(User, engineer_user.id)
        assert user.check_password('password123')

    def test_404(self, admin_client):
        rv = admin_client.get('/admin/users/99999/edit')
        assert rv.status_code == 404

    def test_audit_log(self, admin_client, engineer_user, db):
        admin_client.post(f'/admin/users/{engineer_user.id}/edit', data={
            'role': ROLE_ADMIN,
        })
        entry = AuditLog.query.filter_by(action='update_user').first()
        assert entry is not None

    def test_requires_admin(self, logged_in_client, engineer_user):
        rv = logged_in_client.get(f'/admin/users/{engineer_user.id}/edit')
        assert rv.status_code == 302


class TestDeleteUser:
    def test_success(self, admin_client, engineer_user, db):
        uid = engineer_user.id
        rv = admin_client.post(f'/admin/users/{uid}/delete', follow_redirects=True)
        assert rv.status_code == 200
        assert db.session.get(User, uid) is None

    def test_cannot_delete_self(self, admin_client, admin_user, db):
        rv = admin_client.post(f'/admin/users/{admin_user.id}/delete', follow_redirects=True)
        assert rv.status_code == 200
        assert db.session.get(User, admin_user.id) is not None

    def test_404(self, admin_client):
        rv = admin_client.post('/admin/users/99999/delete')
        assert rv.status_code == 404

    def test_audit_log(self, admin_client, engineer_user, db):
        admin_client.post(f'/admin/users/{engineer_user.id}/delete')
        entry = AuditLog.query.filter_by(action='delete_user').first()
        assert entry is not None

    def test_requires_admin(self, logged_in_client, engineer_user):
        rv = logged_in_client.post(f'/admin/users/{engineer_user.id}/delete')
        assert rv.status_code == 302


class TestAuditLogPage:
    def test_renders(self, admin_client):
        rv = admin_client.get('/admin/audit')
        assert rv.status_code == 200

    def test_shows_entries(self, admin_client, app, db, admin_user):
        with app.test_request_context():
            from flask_login import login_user
            login_user(admin_user)
            AuditLog.log('login')
        rv = admin_client.get('/admin/audit')
        assert rv.status_code == 200

    def test_user_filter(self, admin_client):
        rv = admin_client.get('/admin/audit?user=admin1')
        assert rv.status_code == 200

    def test_action_filter(self, admin_client):
        rv = admin_client.get('/admin/audit?action=login')
        assert rv.status_code == 200

    def test_requires_admin(self, logged_in_client):
        rv = logged_in_client.get('/admin/audit')
        assert rv.status_code == 302


class TestSettings:
    def test_renders(self, admin_client):
        rv = admin_client.get('/admin/settings')
        assert rv.status_code == 200

    def test_save(self, admin_client, db):
        rv = admin_client.post('/admin/settings', data={
            'comsol_path': '/opt/comsol',
            'max_upload_size_mb': '100',
            'simulation_timeout_seconds': '7200',
            'maintenance_message': 'Offline',
        }, follow_redirects=True)
        assert rv.status_code == 200
        assert SystemSetting.get('max_upload_size_mb') == 100

    def test_bool_toggle(self, admin_client, db):
        admin_client.post('/admin/settings', data={
            'maintenance_mode': 'on',
            'comsol_path': '/usr/local/comsol',
            'max_upload_size_mb': '50',
            'simulation_timeout_seconds': '3600',
            'maintenance_message': 'Test',
        })
        assert SystemSetting.get('maintenance_mode') is True

    def test_requires_admin(self, logged_in_client):
        rv = logged_in_client.get('/admin/settings')
        assert rv.status_code == 302

    def test_maintenance_mode_blocks_engineers(self, client, db, admin_user, engineer_user):
        """Set maintenance mode via admin, then login as engineer to verify block."""
        # Login as admin, enable maintenance
        client.post('/auth/login', data={
            'username': 'admin1', 'password': 'adminpass'})
        client.post('/admin/settings', data={
            'maintenance_mode': 'on',
            'comsol_path': '/usr/local/comsol',
            'max_upload_size_mb': '50',
            'simulation_timeout_seconds': '3600',
            'maintenance_message': 'Under maintenance',
        })
        client.get('/auth/logout')
        # Login as engineer
        client.post('/auth/login', data={
            'username': 'engineer1', 'password': 'password123'})
        rv = client.get('/')
        assert rv.status_code == 503


class TestMaterialChanges:
    def test_renders(self, admin_client):
        rv = admin_client.get('/admin/material-changes')
        assert rv.status_code == 200

    def test_requires_admin(self, logged_in_client):
        rv = logged_in_client.get('/admin/material-changes')
        assert rv.status_code == 302

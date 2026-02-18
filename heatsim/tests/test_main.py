"""Tests for main dashboard routes."""
import pytest
from app.models import Simulation, SystemSetting


class TestDashboard:
    def test_renders(self, logged_in_client):
        rv = logged_in_client.get('/')
        assert rv.status_code == 200

    def test_requires_login(self, client, db):
        rv = client.get('/')
        assert rv.status_code == 302

    def test_shows_stats(self, logged_in_client, sample_simulation):
        rv = logged_in_client.get('/')
        assert rv.status_code == 200
        # Page should contain some simulation-related text
        assert b'simulation' in rv.data.lower() or b'Simulation' in rv.data

    def test_shows_recent_sims(self, logged_in_client, sample_simulation):
        rv = logged_in_client.get('/')
        assert b'Test Sim' in rv.data

    def test_empty_state(self, logged_in_client):
        """Dashboard works with no simulations."""
        rv = logged_in_client.get('/')
        assert rv.status_code == 200

    def test_maintenance_mode_503(self, client, db, admin_user, engineer_user):
        """Engineer sees 503 when maintenance is on."""
        # Login as admin, set maintenance mode
        client.post('/auth/login', data={
            'username': 'admin1', 'password': 'adminpass'})
        SystemSetting.set('maintenance_mode', 'true', value_type='bool')
        client.get('/auth/logout')
        # Login as engineer
        client.post('/auth/login', data={
            'username': 'engineer1', 'password': 'password123'})
        rv = client.get('/')
        assert rv.status_code == 503

    def test_admin_bypasses_maintenance(self, client, db, admin_user):
        client.post('/auth/login', data={
            'username': 'admin1', 'password': 'adminpass'})
        SystemSetting.set('maintenance_mode', 'true', value_type='bool')
        rv = client.get('/')
        assert rv.status_code == 200

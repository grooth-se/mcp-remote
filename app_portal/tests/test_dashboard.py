"""Tests for dashboard and app launcher."""
from unittest.mock import patch
from app.models.permission import UserPermission


def test_dashboard_requires_login(client):
    resp = client.get('/', follow_redirects=True)
    assert b'Sign In' in resp.data


def test_dashboard_shows_apps_for_admin(logged_in_client, sample_apps):
    with patch('app.routes.dashboard.check_health', return_value=False):
        resp = logged_in_client.get('/')
    assert resp.status_code == 200
    assert b'Accrued Income' in resp.data
    assert b'HeatSim' in resp.data
    assert b'Durabler2' in resp.data


def test_dashboard_shows_only_permitted_apps(user_logged_in_client, db, normal_user, sample_apps):
    perm = UserPermission(user_id=normal_user.id, app_id=sample_apps[0].id)
    db.session.add(perm)
    db.session.commit()

    with patch('app.routes.dashboard.check_health', return_value=False):
        resp = user_logged_in_client.get('/')
    assert b'Accrued Income' in resp.data
    assert b'HeatSim' not in resp.data


def test_dashboard_empty_for_user_without_perms(user_logged_in_client, sample_apps):
    with patch('app.routes.dashboard.check_health', return_value=False):
        resp = user_logged_in_client.get('/')
    assert b'No applications available' in resp.data


def test_launch_app_admin_local(logged_in_client, sample_app):
    """Local dev mode: redirects directly to app's internal_url."""
    with patch('app.routes.dashboard.check_health', return_value=True):
        resp = logged_in_client.get(f'/launch/{sample_app.app_code}')
    assert resp.status_code == 302
    assert 'http://localhost:9999/?token=' in resp.location


def test_launch_app_admin_behind_proxy(app, logged_in_client, sample_app):
    """Behind proxy: redirects to /app/<code>/ prefix path."""
    app.config['BEHIND_PROXY'] = True
    with patch('app.routes.dashboard.check_health', return_value=True):
        resp = logged_in_client.get(f'/launch/{sample_app.app_code}')
    assert resp.status_code == 302
    assert '/app/testapp/?token=' in resp.location


def test_launch_app_offline(logged_in_client, sample_app):
    with patch('app.routes.dashboard.check_health', return_value=False):
        resp = logged_in_client.get(f'/launch/{sample_app.app_code}', follow_redirects=True)
    assert b'currently offline' in resp.data


def test_launch_app_no_permission(user_logged_in_client, sample_app):
    resp = user_logged_in_client.get(f'/launch/{sample_app.app_code}', follow_redirects=True)
    assert b'do not have permission' in resp.data


def test_launch_nonexistent_app(logged_in_client):
    resp = logged_in_client.get('/launch/noapp')
    assert resp.status_code == 404

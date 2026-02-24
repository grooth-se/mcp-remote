"""Tests for heatsim dashboard."""


def test_dashboard_requires_login(client):
    resp = client.get('/', follow_redirects=True)
    assert b'Log In' in resp.data


def test_dashboard_renders_for_engineer(logged_in_client):
    resp = logged_in_client.get('/')
    assert resp.status_code == 200


def test_dashboard_renders_for_admin(admin_client):
    resp = admin_client.get('/')
    assert resp.status_code == 200

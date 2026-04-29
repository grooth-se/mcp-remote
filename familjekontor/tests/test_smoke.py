"""Smoke tests — proves the Flask app boots and the root route responds."""

from app import create_app


def test_app_creates():
    app = create_app('testing')
    assert app is not None
    assert app.config['TESTING'] is True


def test_index_responds(client):
    resp = client.get('/')
    # 200 (dashboard rendered), 302 (redirect to login), or 401 are all "app is alive".
    assert resp.status_code in (200, 302, 401)


def test_login_route_renders(client):
    resp = client.get('/login')
    assert resp.status_code in (200, 302)

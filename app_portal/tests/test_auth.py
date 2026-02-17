"""Tests for authentication routes."""


def test_login_page_loads(client):
    resp = client.get('/login')
    assert resp.status_code == 200
    assert b'Sign In' in resp.data


def test_login_success(client, admin_user):
    resp = client.post('/login', data={
        'username': 'admin', 'password': 'adminpass'
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert b'Applications' in resp.data


def test_login_wrong_password(client, admin_user):
    resp = client.post('/login', data={
        'username': 'admin', 'password': 'wrongpass'
    }, follow_redirects=True)
    assert b'Invalid username or password' in resp.data


def test_login_nonexistent_user(client):
    resp = client.post('/login', data={
        'username': 'nouser', 'password': 'pass1234'
    }, follow_redirects=True)
    assert b'Invalid username or password' in resp.data


def test_login_inactive_user(client, db, normal_user):
    normal_user.is_active_user = False
    db.session.commit()
    resp = client.post('/login', data={
        'username': 'testuser', 'password': 'testpass1'
    }, follow_redirects=True)
    assert b'Invalid username or password' in resp.data


def test_logout(logged_in_client):
    resp = logged_in_client.get('/logout', follow_redirects=True)
    assert b'logged out' in resp.data


def test_profile_requires_login(client):
    resp = client.get('/profile', follow_redirects=True)
    assert b'Sign In' in resp.data


def test_profile_view(logged_in_client, admin_user):
    resp = logged_in_client.get('/profile')
    assert resp.status_code == 200
    assert b'admin' in resp.data


def test_change_password_page(logged_in_client):
    resp = logged_in_client.get('/change-password')
    assert resp.status_code == 200
    assert b'Current Password' in resp.data


def test_change_password_success(logged_in_client):
    resp = logged_in_client.post('/change-password', data={
        'current_password': 'adminpass',
        'new_password': 'newpass12',
        'confirm_password': 'newpass12',
    }, follow_redirects=True)
    assert b'Password changed successfully' in resp.data


def test_change_password_wrong_current(logged_in_client):
    resp = logged_in_client.post('/change-password', data={
        'current_password': 'wrongpass',
        'new_password': 'newpass12',
        'confirm_password': 'newpass12',
    }, follow_redirects=True)
    assert b'Current password is incorrect' in resp.data


def test_change_password_mismatch(logged_in_client):
    resp = logged_in_client.post('/change-password', data={
        'current_password': 'adminpass',
        'new_password': 'newpass12',
        'confirm_password': 'different',
    }, follow_redirects=True)
    assert b'Passwords must match' in resp.data


def test_redirect_when_authenticated(logged_in_client):
    resp = logged_in_client.get('/login')
    assert resp.status_code == 302

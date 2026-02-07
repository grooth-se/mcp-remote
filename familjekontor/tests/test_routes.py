"""Tests for route access and basic functionality."""


def test_login_page(client):
    response = client.get('/login')
    assert response.status_code == 200
    assert 'Logga in' in response.data.decode()


def test_redirect_without_login(client):
    response = client.get('/')
    assert response.status_code == 302
    assert '/login' in response.headers.get('Location', '')


def test_login(client, admin_user):
    response = client.post('/login', data={
        'username': 'admin',
        'password': 'testpass123',
    }, follow_redirects=True)
    assert response.status_code == 200


def test_dashboard_after_login(logged_in_client):
    response = logged_in_client.get('/')
    assert response.status_code == 200
    assert 'Välkommen' in response.data.decode() or 'Start' in response.data.decode()


def test_companies_page(logged_in_client):
    response = logged_in_client.get('/companies/')
    assert response.status_code == 200
    assert 'Företag' in response.data.decode()


def test_reports_page(logged_in_client):
    response = logged_in_client.get('/reports/')
    assert response.status_code == 200
    assert 'Rapporter' in response.data.decode()


def test_admin_page(logged_in_client):
    response = logged_in_client.get('/admin/')
    assert response.status_code == 200
    assert 'Administration' in response.data.decode()


def test_sie_page(logged_in_client):
    response = logged_in_client.get('/sie/')
    # Redirects if no active company
    assert response.status_code in (200, 302)

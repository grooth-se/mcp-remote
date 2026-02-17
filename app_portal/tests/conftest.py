import pytest
from app import create_app
from app.config import TestingConfig
from app.extensions import db as _db
from app.models.user import User
from app.models.application import Application
from app.models.permission import UserPermission


@pytest.fixture
def app():
    app = create_app(TestingConfig)
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def db(app):
    return _db


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def admin_user(db):
    user = User(username='admin', display_name='Admin User', is_admin=True)
    user.set_password('adminpass')
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def normal_user(db):
    user = User(username='testuser', display_name='Test User')
    user.set_password('testpass1')
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def sample_app(db):
    application = Application(
        app_code='testapp',
        app_name='Test App',
        description='A test application',
        internal_url='http://localhost:9999',
        icon='bi-app',
        display_order=1,
    )
    db.session.add(application)
    db.session.commit()
    return application


@pytest.fixture
def sample_apps(db):
    apps = []
    for i, (code, name) in enumerate([
        ('accruedincome', 'Accrued Income'),
        ('heatsim', 'HeatSim'),
        ('durabler2', 'Durabler2'),
    ]):
        a = Application(app_code=code, app_name=name,
                        internal_url=f'http://localhost:{5001 + i}',
                        display_order=i + 1)
        db.session.add(a)
        apps.append(a)
    db.session.commit()
    return apps


@pytest.fixture
def logged_in_client(client, admin_user):
    client.post('/login', data={
        'username': 'admin', 'password': 'adminpass'
    }, follow_redirects=True)
    return client


@pytest.fixture
def user_logged_in_client(client, normal_user):
    client.post('/login', data={
        'username': 'testuser', 'password': 'testpass1'
    }, follow_redirects=True)
    return client

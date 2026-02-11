import pytest
from app import create_app, db as _db
from app.models.user import User


@pytest.fixture(scope='session')
def app():
    app = create_app('testing')
    with app.app_context():
        _db.create_all()
        yield app
        _db.drop_all()


@pytest.fixture(scope='function')
def db(app):
    with app.app_context():
        _db.create_all()
        yield _db
        _db.session.rollback()
        for table in reversed(_db.metadata.sorted_tables):
            _db.session.execute(table.delete())
        _db.session.commit()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def admin_user(db):
    user = User(username='admin', email='admin@test.com', role='admin')
    user.set_password('testpass123')
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def logged_in_client(client, admin_user):
    client.post('/login', data={
        'username': 'admin',
        'password': 'testpass123',
    }, follow_redirects=True)
    return client


@pytest.fixture
def readonly_user(db):
    user = User(username='reader', email='reader@test.com', role='readonly')
    user.set_password('testpass123')
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def readonly_client(app, readonly_user):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(readonly_user.id)
        sess['_fresh'] = True
    return client

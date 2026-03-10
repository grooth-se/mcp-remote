import pytest
from app import create_app, db as _db


@pytest.fixture
def app():
    app = create_app('testing')
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
def logged_in_client(app, db):
    from app.models.user import User
    user = User(username='testuser', display_name='Test User', is_admin=False)
    user.set_password('test')
    db.session.add(user)
    db.session.commit()

    client = app.test_client()
    with client.session_transaction() as sess:
        sess['portal_user'] = 'testuser'
        sess['_user_id'] = str(user.id)
    return client

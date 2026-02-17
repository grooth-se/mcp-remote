"""Test fixtures for MG5 Integration Service."""

import os
import pytest
from app import create_app
from app.extensions import db as _db


@pytest.fixture(scope='session')
def app():
    """Create Flask application for testing."""
    app = create_app('testing')
    return app


@pytest.fixture(scope='function')
def db(app):
    """Provide a clean database for each test."""
    with app.app_context():
        _db.create_all()
        yield _db
        _db.session.rollback()
        _db.drop_all()


@pytest.fixture(scope='function')
def client(app, db):
    """Provide a test client."""
    return app.test_client()


@pytest.fixture(scope='session')
def fixtures_dir():
    """Path to test fixture Excel files."""
    return os.path.join(os.path.dirname(__file__), 'fixtures')

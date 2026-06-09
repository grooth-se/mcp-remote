import os
from datetime import timedelta

basedir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-change-in-production')
    DATABASE_PATH = os.environ.get('DATABASE_PATH', os.path.join(basedir, 'data', 'portal.db'))
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{os.environ.get('DATABASE_PATH', os.path.join(basedir, 'data', 'portal.db'))}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Session
    # Distinct cookie name so the portal's login session is not overwritten by
    # apps served on the same origin under /app/<code>/. Every Flask app behind
    # nginx otherwise defaults to a cookie named "session" at path "/", and they
    # clobber each other. See also each app's init_portal_auth().
    SESSION_COOKIE_NAME = 'portal_session'
    SESSION_LIFETIME_HOURS = int(os.environ.get('SESSION_LIFETIME', 24))
    REMEMBER_ME_DAYS = int(os.environ.get('REMEMBER_ME_DAYS', 7))
    PERMANENT_SESSION_LIFETIME = timedelta(hours=int(os.environ.get('SESSION_LIFETIME', 24)))

    # Token
    TOKEN_EXPIRY_HOURS = int(os.environ.get('TOKEN_EXPIRY', 24))

    # Password
    MIN_PASSWORD_LENGTH = 8

    # Portal
    PORTAL_NAME = "Subseatec Applications"

    # App health check
    HEALTH_CHECK_TIMEOUT = 3  # seconds

    # Set True when running behind nginx reverse proxy (Docker deployment)
    # When False (local dev), launch redirects directly to app's internal_url
    BEHIND_PROXY = os.environ.get('BEHIND_PROXY', 'false').lower() == 'true'


class TestingConfig(Config):
    TESTING = True
    SECRET_KEY = 'test-secret-key'
    SQLALCHEMY_DATABASE_URI = 'sqlite://'  # in-memory
    WTF_CSRF_ENABLED = False
    SERVER_NAME = 'localhost'

import os

basedir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-change-in-production')
    DATABASE_PATH = os.environ.get('DATABASE_PATH', os.path.join(basedir, 'data', 'portal.db'))
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{os.environ.get('DATABASE_PATH', os.path.join(basedir, 'data', 'portal.db'))}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Session
    SESSION_LIFETIME_HOURS = int(os.environ.get('SESSION_LIFETIME', 8))
    REMEMBER_ME_DAYS = int(os.environ.get('REMEMBER_ME_DAYS', 7))

    # Token
    TOKEN_EXPIRY_HOURS = int(os.environ.get('TOKEN_EXPIRY', 8))

    # Password
    MIN_PASSWORD_LENGTH = 8

    # Portal
    PORTAL_NAME = "Subseatec Applications"

    # App health check
    HEALTH_CHECK_TIMEOUT = 3  # seconds


class TestingConfig(Config):
    TESTING = True
    SECRET_KEY = 'test-secret-key'
    SQLALCHEMY_DATABASE_URI = 'sqlite://'  # in-memory
    WTF_CSRF_ENABLED = False
    SERVER_NAME = 'localhost'

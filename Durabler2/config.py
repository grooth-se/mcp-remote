"""Flask application configuration."""
import os
from pathlib import Path

basedir = Path(__file__).parent.absolute()


def _get_database_url():
    """Get database URL, fixing postgres:// -> postgresql:// if needed."""
    url = os.environ.get('DATABASE_URL')
    if url and url.startswith('postgres://'):
        url = url.replace('postgres://', 'postgresql://', 1)
    return url


class Config:
    """Base configuration."""
    # Secret key for session management (change in production!)
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'

    # Database
    SQLALCHEMY_DATABASE_URI = _get_database_url() or \
        f"sqlite:///{basedir / 'instance' / 'durabler.db'}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # File uploads (inside static folder for web access)
    UPLOAD_FOLDER = basedir / 'app' / 'static' / 'uploads'
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50 MB max upload
    ALLOWED_EXTENSIONS = {'csv', 'xlsx', 'xls', 'png', 'jpg', 'jpeg', 'gif'}

    # Reports output
    REPORTS_FOLDER = basedir / 'reports'

    # PDF Signing (X.509 certificates)
    CERTS_FOLDER = basedir / 'certs'
    COMPANY_CERT_FILE = os.environ.get('COMPANY_CERT_FILE') or 'durabler_company.p12'
    COMPANY_CERT_PASSWORD = os.environ.get('COMPANY_CERT_PASSWORD') or ''

    # Session
    PERMANENT_SESSION_LIFETIME = 3600  # 1 hour


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True


class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False
    # In production, set SECRET_KEY via environment variable


class TestingConfig(Config):
    """Testing configuration."""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}

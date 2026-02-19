"""Flask application configuration."""

import os
from pathlib import Path

basedir = Path(__file__).parent.absolute()


class Config:
    """Base configuration."""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'accrued-income-dev-key'

    # Database
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        f"sqlite:///{basedir / 'instance' / 'accrued.db'}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # File handling
    UPLOAD_FOLDER = basedir / 'app' / 'static' / 'uploads'
    OUTPUT_FOLDER = basedir / 'output'
    CHARTS_FOLDER = basedir / 'output' / 'charts'
    MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100 MB
    ALLOWED_EXTENSIONS = {'xlsx', 'xls'}

    # Calculation parameters (from legacy code)
    COMPLETION_THRESHOLD = 0.99  # cc = 0.99
    HOUR_COST = 475  # SEK per hour for time tracking

    # Portal authentication
    PORTAL_AUTH_ENABLED = os.environ.get('PORTAL_AUTH_ENABLED', 'false').lower() == 'true'
    PORTAL_URL = os.environ.get('PORTAL_URL', 'http://portal:5000')
    PORTAL_EXTERNAL_URL = os.environ.get('PORTAL_EXTERNAL_URL', '/')
    APP_CODE = 'accruedincome'

    # MG5 Integration API
    MG5_INTEGRATION_URL = os.environ.get('MG5_INTEGRATION_URL', 'http://mg5integration:5001')

    # Session
    PERMANENT_SESSION_LIFETIME = 8 * 60 * 60  # 8 hours


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True


class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}

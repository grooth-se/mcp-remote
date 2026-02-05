"""Flask application configuration with dual database support."""
import os
from pathlib import Path

basedir = Path(__file__).parent.absolute()


class Config:
    """Base configuration."""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'

    # SQLite for user management (primary database for Flask-SQLAlchemy)
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        f"sqlite:///{basedir / 'instance' / 'users.db'}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # PostgreSQL for materials/simulations (secondary database - Phase 2)
    POSTGRES_HOST = os.environ.get('POSTGRES_HOST', 'localhost')
    POSTGRES_PORT = os.environ.get('POSTGRES_PORT', '5432')
    POSTGRES_DB = os.environ.get('POSTGRES_DB', 'subseatec_sim')
    POSTGRES_USER = os.environ.get('POSTGRES_USER', 'subseatec')
    POSTGRES_PASSWORD = os.environ.get('POSTGRES_PASSWORD', '')

    @property
    def POSTGRES_URI(self):
        """Build PostgreSQL connection URI."""
        if self.POSTGRES_PASSWORD:
            return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        return f"postgresql://{self.POSTGRES_USER}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    # Bind multiple databases (Phase 2 will populate this)
    SQLALCHEMY_BINDS = {}

    # Session
    PERMANENT_SESSION_LIFETIME = 3600  # 1 hour

    # Paths
    UPLOAD_FOLDER = basedir / 'data' / 'uploads'
    GEOMETRY_FOLDER = basedir / 'data' / 'geometries'
    RESULTS_FOLDER = basedir / 'data' / 'results'

    # COMSOL (Phase 4)
    COMSOL_PATH = os.environ.get('COMSOL_PATH', '/usr/local/comsol')
    COMSOL_LICENSE_SERVER = os.environ.get('COMSOL_LICENSE', '')


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True


class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False


class TestingConfig(Config):
    """Testing configuration."""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}

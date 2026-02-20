"""Flask application configuration with dual database support."""
import os
from pathlib import Path

basedir = Path(__file__).parent.absolute()


class Config:
    """Base configuration."""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'

    # Portal authentication
    PORTAL_AUTH_ENABLED = os.environ.get("PORTAL_AUTH_ENABLED", "false").lower() == "true"
    PORTAL_URL = os.environ.get("PORTAL_URL", "http://portal:5000")
    PORTAL_EXTERNAL_URL = os.environ.get("PORTAL_EXTERNAL_URL", "/")

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

    # Bind multiple databases - set dynamically in app factory
    SQLALCHEMY_BINDS = None

    # Session
    PERMANENT_SESSION_LIFETIME = 3600  # 1 hour

    # Paths
    UPLOAD_FOLDER = basedir / 'data' / 'uploads'
    GEOMETRY_FOLDER = basedir / 'data' / 'geometries'
    RESULTS_FOLDER = basedir / 'data' / 'results'
    VTK_FOLDER = basedir / 'data' / 'vtk'
    ANIMATIONS_FOLDER = basedir / 'data' / 'animations'
    COMSOL_MODELS_FOLDER = basedir / 'data' / 'comsol_models'

    # COMSOL (Phase 4)
    COMSOL_PATH = os.environ.get('COMSOL_PATH', '/usr/local/comsol')
    COMSOL_LICENSE_SERVER = os.environ.get('COMSOL_LICENSE', '')
    COMSOL_TIMEOUT = int(os.environ.get('COMSOL_TIMEOUT', 3600))  # 1 hour default
    COMSOL_CORES = int(os.environ.get('COMSOL_CORES', 4))  # CPU cores for COMSOL


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
    SQLALCHEMY_BINDS = {'materials': 'sqlite://'}
    WTF_CSRF_ENABLED = False
    PORTAL_AUTH_ENABLED = False


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}

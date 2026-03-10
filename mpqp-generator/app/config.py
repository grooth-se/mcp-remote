import os

basedir = os.path.abspath(os.path.dirname(__file__))
project_dir = os.path.dirname(basedir)


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

    # PostgreSQL
    POSTGRES_HOST = os.environ.get('POSTGRES_HOST', 'localhost')
    POSTGRES_PORT = os.environ.get('POSTGRES_PORT', '5432')
    POSTGRES_DB = os.environ.get('POSTGRES_DB', 'mpqp_generator')
    POSTGRES_USER = os.environ.get('POSTGRES_USER', 'mpqp')
    POSTGRES_PASSWORD = os.environ.get('POSTGRES_PASSWORD', 'mpqp')
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL',
        f'postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Ollama (Local LLM)
    OLLAMA_HOST = os.environ.get('OLLAMA_HOST', 'http://localhost:11434')
    LLM_MODEL = os.environ.get('LLM_MODEL', 'llama3.1:8b')
    EMBEDDING_MODEL = os.environ.get('EMBEDDING_MODEL', 'nomic-embed-text')

    # Vector Database (ChromaDB)
    VECTOR_DB_PATH = os.environ.get('VECTOR_DB_PATH', os.path.join(project_dir, 'data', 'vectordb'))

    # Paths
    HISTORICAL_PROJECTS_PATH = os.environ.get('HISTORICAL_PATH', os.path.join(project_dir, 'data', 'historical_projects'))
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', os.path.join(project_dir, 'data', 'new_projects'))
    GENERATED_FOLDER = os.environ.get('GENERATED_FOLDER', os.path.join(project_dir, 'data', 'generated'))
    TEMPLATE_FOLDER_PATH = os.environ.get('TEMPLATE_FOLDER', os.path.join(project_dir, 'data', 'templates'))

    # Processing
    CHUNK_SIZE = 1000
    CHUNK_OVERLAP = 200
    MAX_SIMILAR_PROJECTS = 10
    MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB max upload

    # LLM Settings
    LLM_TEMPERATURE = 0.3
    LLM_MAX_TOKENS = 4096

    # Portal auth
    PORTAL_URL = os.environ.get('PORTAL_URL', 'http://portal:5000')
    PORTAL_EXTERNAL_URL = os.environ.get('PORTAL_EXTERNAL_URL', '/')
    APP_CODE = os.environ.get('APP_CODE', 'mpqpgenerator')


class DevelopmentConfig(Config):
    DEBUG = True


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'


class ProductionConfig(Config):
    DEBUG = False
    WTF_CSRF_TIME_LIMIT = None  # No expiry — tokens valid for session lifetime
    SESSION_COOKIE_SAMESITE = 'Lax'


config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
}

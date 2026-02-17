import os

basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Local storage
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL',
        'sqlite:///' + os.path.join(basedir, 'instance', 'monitor_data.db')
    )

    # Excel exports folder
    EXCEL_EXPORTS_FOLDER = os.environ.get(
        'EXCEL_EXPORTS_FOLDER',
        os.path.join(basedir, 'data', 'excel_exports')
    )

    # Monitor G5 ODBC Connection (future use)
    MONITOR_HOST = os.environ.get('MONITOR_HOST', '172.27.55.101')
    MONITOR_PORT = os.environ.get('MONITOR_PORT', '2638')
    MONITOR_DATABASE = os.environ.get('MONITOR_DATABASE', '001.1')
    MONITOR_USER = os.environ.get('MONITOR_USER', 'ReadOnlyUser')
    MONITOR_PASSWORD = os.environ.get('MONITOR_PASSWORD', '')
    MONITOR_DRIVER = os.environ.get('MONITOR_DRIVER', 'SQL Anywhere 17')

    # Scheduling
    EXTRACTION_SCHEDULE = os.environ.get('EXTRACTION_SCHEDULE', '06:00')

    # API
    API_HOST = os.environ.get('API_HOST', '0.0.0.0')
    API_PORT = int(os.environ.get('API_PORT', 5001))

    @property
    def monitor_connection_string(self):
        return (
            f"DRIVER={{{self.MONITOR_DRIVER}}};"
            f"HOST={self.MONITOR_HOST}:{self.MONITOR_PORT};"
            f"DATABASE={self.MONITOR_DATABASE};"
            f"UID={self.MONITOR_USER};"
            f"PWD={self.MONITOR_PASSWORD};"
        )


class DevelopmentConfig(Config):
    DEBUG = True


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite://'  # in-memory
    EXCEL_EXPORTS_FOLDER = os.path.join(basedir, 'tests', 'fixtures')


class ProductionConfig(Config):
    DEBUG = False


config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}

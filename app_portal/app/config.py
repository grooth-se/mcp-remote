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

    # Admin monitoring
    # Read-only docker-socket-proxy URL; empty = container stats hidden
    DOCKER_PROXY_URL = os.environ.get('DOCKER_PROXY_URL', '')
    MONITOR_POLL_SECONDS = int(os.environ.get('MONITOR_POLL_SECONDS', 5))
    COLLECT_INTERVAL_SECONDS = int(os.environ.get('COLLECT_INTERVAL_SECONDS', 60))

    # Retention windows (days)
    METRICS_RAW_DAYS = int(os.environ.get('METRICS_RAW_DAYS', 7))
    METRICS_HOURLY_DAYS = int(os.environ.get('METRICS_HOURLY_DAYS', 90))
    ACCESS_LOG_RETENTION_DAYS = int(os.environ.get('ACCESS_LOG_RETENTION_DAYS', 90))

    # Cap on streamed usage CSV export rows
    USAGE_EXPORT_MAX_ROWS = int(os.environ.get('USAGE_EXPORT_MAX_ROWS', 100000))

    # Set True when running behind nginx reverse proxy (Docker deployment)
    # When False (local dev), launch redirects directly to app's internal_url
    BEHIND_PROXY = os.environ.get('BEHIND_PROXY', 'false').lower() == 'true'


class TestingConfig(Config):
    TESTING = True
    SECRET_KEY = 'test-secret-key'
    SQLALCHEMY_DATABASE_URI = 'sqlite://'  # in-memory
    WTF_CSRF_ENABLED = False
    SERVER_NAME = 'localhost'

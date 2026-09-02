"""Flask extensions initialization."""
from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from sqlalchemy import event
from sqlalchemy.engine import Engine
import sqlite3


def utcnow():
    """Naive UTC timestamp (replacement for deprecated datetime.utcnow).

    Stored DateTime columns hold naive UTC values; keep that convention.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)

# Database
db = SQLAlchemy()

# Login manager
login_manager = LoginManager()

# Database migrations
migrate = Migrate()


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):
    # SQLite ships with foreign_keys OFF by default; enable so ON DELETE CASCADE fires.
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

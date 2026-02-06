"""Flask extensions initialization."""
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect

# Database (SQLite for users, PostgreSQL binds added in Phase 2)
db = SQLAlchemy()

# Login manager
login_manager = LoginManager()

# Database migrations
migrate = Migrate()

# CSRF protection
csrf = CSRFProtect()

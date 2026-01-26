"""Flask extensions initialization."""
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate

# Database
db = SQLAlchemy()

# Login manager
login_manager = LoginManager()

# Database migrations
migrate = Migrate()

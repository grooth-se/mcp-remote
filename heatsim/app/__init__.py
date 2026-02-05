"""Flask application factory."""
import os
from flask import Flask
from config import config

from .extensions import db, login_manager, migrate


def create_app(config_name='default'):
    """Create and configure the Flask application.

    Parameters
    ----------
    config_name : str
        Configuration name: 'development', 'production', 'testing'

    Returns
    -------
    Flask
        Configured Flask application instance
    """
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # Ensure folders exist
    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(app.config.get('UPLOAD_FOLDER', 'data/uploads'), exist_ok=True)
    os.makedirs(app.config.get('GEOMETRY_FOLDER', 'data/geometries'), exist_ok=True)
    os.makedirs(app.config.get('RESULTS_FOLDER', 'data/results'), exist_ok=True)

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    # Configure login
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'

    # Import models for migrations
    from . import models  # noqa: F401

    # Register blueprints
    from .main import main_bp
    from .auth import auth_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix='/auth')

    # Create database tables
    with app.app_context():
        db.create_all()

    return app

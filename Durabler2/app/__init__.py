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

    # Ensure instance folder exists
    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['REPORTS_FOLDER'], exist_ok=True)

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    # Configure login
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'

    # Register blueprints
    from .main import main_bp
    from .auth import auth_bp
    from .tensile import tensile_bp
    from .sonic import sonic_bp
    from .fcgr import fcgr_bp
    from .ctod import ctod_bp
    from .certificates import certificates_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(tensile_bp, url_prefix='/tensile')
    app.register_blueprint(sonic_bp, url_prefix='/sonic')
    app.register_blueprint(fcgr_bp, url_prefix='/fcgr')
    app.register_blueprint(ctod_bp, url_prefix='/ctod')
    app.register_blueprint(certificates_bp, url_prefix='/certificates')

    # Create database tables (development only)
    with app.app_context():
        db.create_all()

    return app

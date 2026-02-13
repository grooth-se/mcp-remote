"""Flask application factory."""
import os
from flask import Flask
from config import config

from .extensions import db, login_manager, migrate, csrf


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
    config_obj = config[config_name]
    app.config.from_object(config_obj)

    # Configure PostgreSQL binds for materials database (Phase 2)
    # Falls back to SQLite in development if PostgreSQL not configured
    postgres_password = os.environ.get('POSTGRES_PASSWORD', '')
    if postgres_password:
        postgres_uri = config_obj().POSTGRES_URI
        app.config['SQLALCHEMY_BINDS'] = {'materials': postgres_uri}
    else:
        # Fallback to SQLite for development without PostgreSQL
        materials_db = os.path.join(app.instance_path, 'materials.db')
        app.config['SQLALCHEMY_BINDS'] = {'materials': f'sqlite:///{materials_db}'}

    # Ensure folders exist
    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(app.config.get('UPLOAD_FOLDER', 'data/uploads'), exist_ok=True)
    os.makedirs(app.config.get('GEOMETRY_FOLDER', 'data/geometries'), exist_ok=True)
    os.makedirs(app.config.get('RESULTS_FOLDER', 'data/results'), exist_ok=True)
    os.makedirs(app.config.get('VTK_FOLDER', 'data/vtk'), exist_ok=True)
    os.makedirs(app.config.get('ANIMATIONS_FOLDER', 'data/animations'), exist_ok=True)
    os.makedirs(app.config.get('COMSOL_MODELS_FOLDER', 'data/comsol_models'), exist_ok=True)

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)

    # Configure login
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'

    # Import models for migrations
    from . import models  # noqa: F401

    # Register blueprints
    from .main import main_bp
    from .auth import auth_bp
    from .materials import materials_bp
    from .simulation import simulation_bp
    from .welding import welding_bp
    from .ht_templates import ht_templates_bp
    from .measured import measured_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(materials_bp, url_prefix='/materials')
    app.register_blueprint(simulation_bp, url_prefix='/simulation')
    app.register_blueprint(welding_bp, url_prefix='/welding')
    app.register_blueprint(ht_templates_bp, url_prefix='/templates')
    app.register_blueprint(measured_bp, url_prefix='/measured')

    # Create database tables
    with app.app_context():
        db.create_all()

    return app

"""Flask application factory."""
import os
from flask import Flask, render_template, request as flask_request
from flask_login import current_user
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

    # Portal auth middleware (ScriptNameMiddleware + token validation)
    from .portal_auth import init_portal_auth
    init_portal_auth(app)

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
    from .admin import admin_bp
    from .api import api_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(materials_bp, url_prefix='/materials')
    app.register_blueprint(simulation_bp, url_prefix='/simulation')
    app.register_blueprint(welding_bp, url_prefix='/welding')
    app.register_blueprint(ht_templates_bp, url_prefix='/templates')
    app.register_blueprint(measured_bp, url_prefix='/measured')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(api_bp, url_prefix='/api')

    # Create database tables
    with app.app_context():
        db.create_all()

        # Ensure new columns exist in materials DB (for upgrades without migration)
        try:
            import sqlalchemy as sa
            mat_engine = db.engines.get('materials')
            if mat_engine:
                inspector = sa.inspect(mat_engine)
                if 'steel_compositions' in inspector.get_table_names():
                    cols = [c['name'] for c in inspector.get_columns('steel_compositions')]
                    if 'hollomon_jaffe_c' not in cols:
                        with mat_engine.connect() as conn:
                            conn.execute(sa.text(
                                'ALTER TABLE steel_compositions ADD COLUMN hollomon_jaffe_c FLOAT DEFAULT 20.0'
                            ))
                            conn.commit()
        except Exception:
            pass  # Non-critical — column may already exist

        # Reset any simulations stuck in 'running' status (from worker crashes/timeouts)
        # Leave 'queued' jobs as-is so the worker re-picks them up
        try:
            mat_engine = db.engines.get('materials')
            if mat_engine:
                with mat_engine.connect() as conn:
                    result = conn.execute(sa.text(
                        "UPDATE simulations SET status = 'failed', "
                        "error_message = 'Server restarted while simulation was running' "
                        "WHERE status = 'running'"
                    ))
                    weld_result = conn.execute(sa.text(
                        "UPDATE weld_projects SET status = 'failed', "
                        "error_message = 'Server restarted while simulation was running' "
                        "WHERE status = 'running'"
                    ))
                    total = result.rowcount + weld_result.rowcount
                    if total > 0:
                        conn.commit()
                        app.logger.info(
                            f'Reset {total} stuck job(s) to failed'
                        )
        except Exception:
            pass  # Table may not exist yet

        # Start background job queue worker thread
        from app.services.job_queue import start_worker
        start_worker(app)

    # Maintenance mode handler
    @app.before_request
    def check_maintenance_mode():
        from .models import SystemSetting
        # Whitelist: auth routes, static files, admin routes
        endpoint = flask_request.endpoint or ''
        if (endpoint.startswith('auth.') or endpoint.startswith('admin.')
                or endpoint == 'static'):
            return None
        if SystemSetting.get('maintenance_mode', False):
            if current_user.is_authenticated and current_user.is_admin:
                return None
            message = SystemSetting.get(
                'maintenance_message',
                'The system is currently under maintenance. Please try again later.'
            )
            return render_template('maintenance.html', message=message), 503

    return app

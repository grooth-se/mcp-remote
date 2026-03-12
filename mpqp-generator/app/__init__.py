import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import event

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()


def create_app(config_name=None):
    app = Flask(__name__)

    if config_name is None:
        config_name = os.environ.get('FLASK_CONFIG', 'development')

    from app.config import config
    app.config.from_object(config[config_name])

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)

    login_manager.login_view = 'main.login'

    from app.models.user import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # Register blueprints
    from app.routes.main import main_bp
    from app.routes.upload import upload_bp
    from app.routes.admin import admin_bp
    from app.routes.generate import generate_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(upload_bp, url_prefix='/upload')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(generate_bp, url_prefix='/generate')


    # Health endpoint for portal and Docker
    @app.route('/health')
    def health():
        result = {'status': 'ok', 'app': 'mpqp-generator'}
        try:
            db.session.execute(db.text('SELECT 1'))
            result['database'] = 'ok'
        except Exception:
            result['database'] = 'error'
            result['status'] = 'degraded'
        return result, 200

    # Portal auth middleware
    portal_auth_enabled = os.environ.get('PORTAL_AUTH_ENABLED', 'false').lower() == 'true'
    if portal_auth_enabled:
        from app.portal_auth import init_portal_auth
        init_portal_auth(app)

    # Enable WAL mode for SQLite (allows concurrent reads during writes)
    if app.config['SQLALCHEMY_DATABASE_URI'].startswith('sqlite'):
        with app.app_context():
            @event.listens_for(db.engine, 'connect')
            def _set_sqlite_wal(dbapi_conn, connection_record):
                cursor = dbapi_conn.cursor()
                cursor.execute('PRAGMA journal_mode=WAL')
                cursor.close()

    # Ensure upload directories exist and seed admin user
    with app.app_context():
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        os.makedirs(app.config['GENERATED_FOLDER'], exist_ok=True)

        # Create default admin if no users exist
        try:
            if User.query.count() == 0:
                admin = User(username='admin', display_name='Admin', is_admin=True)
                admin.set_password('admin')
                db.session.add(admin)
                db.session.commit()
        except Exception:
            pass

    return app

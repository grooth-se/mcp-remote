from flask import Flask
from app.config import Config
from app.extensions import db, login_manager, csrf


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    # Register blueprints
    from app.routes.auth import auth_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.api import api_bp
    from app.routes.admin.users import admin_users_bp
    from app.routes.admin.apps import admin_apps_bp
    from app.routes.admin.permissions import admin_permissions_bp
    from app.routes.admin.system import admin_system_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(admin_users_bp, url_prefix='/admin/users')
    app.register_blueprint(admin_apps_bp, url_prefix='/admin/apps')
    app.register_blueprint(admin_permissions_bp, url_prefix='/admin/permissions')
    app.register_blueprint(admin_system_bp, url_prefix='/admin/system')

    # Exempt API from CSRF
    csrf.exempt(api_bp)

    # User loader for Flask-Login
    from app.models.user import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # Create tables
    with app.app_context():
        from app.models import user, application, permission, session, log  # noqa: F401
        db.create_all()

    return app

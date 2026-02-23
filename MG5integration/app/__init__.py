from flask import Flask, redirect, url_for
from config import config
from app.extensions import db


def create_app(config_name='default'):
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # Portal auth middleware (ScriptNameMiddleware + token validation)
    from app.portal_auth import init_portal_auth
    init_portal_auth(app)

    db.init_app(app)

    # Register blueprints
    from app.api import api_bp
    app.register_blueprint(api_bp, url_prefix='/api')

    from app.admin import admin_bp
    app.register_blueprint(admin_bp, url_prefix='/admin')

    from app.review import review_bp
    app.register_blueprint(review_bp, url_prefix='/review')

    @app.route('/')
    def index():
        return redirect(url_for('admin.dashboard'))

    # Create tables only if database doesn't exist yet
    with app.app_context():
        from app import models  # noqa: F401
        import os
        db_path = app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
        if not os.path.exists(db_path):
            db.create_all()

        # Mark any stale 'running' imports as interrupted (e.g. after crash)
        from app.services.import_service import ImportService
        cleaned = ImportService.cleanup_stale_runs()
        if cleaned:
            app.logger.warning(f'Marked {cleaned} stale extraction(s) as interrupted')

    return app

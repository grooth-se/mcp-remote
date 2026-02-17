from flask import Flask
from config import config
from app.extensions import db


def create_app(config_name='default'):
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    db.init_app(app)

    # Register blueprints
    from app.api import api_bp
    app.register_blueprint(api_bp, url_prefix='/api')

    from app.admin import admin_bp
    app.register_blueprint(admin_bp, url_prefix='/admin')

    # Create tables
    with app.app_context():
        from app import models  # noqa: F401
        db.create_all()

    return app

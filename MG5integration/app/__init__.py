from flask import Flask
from config import config
from app.extensions import db


class ReverseProxyMiddleware:
    """Handle X-Script-Name header for reverse proxy prefix."""

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        script_name = environ.get('HTTP_X_SCRIPT_NAME', '')
        if script_name:
            environ['SCRIPT_NAME'] = script_name
            path_info = environ.get('PATH_INFO', '')
            if path_info.startswith(script_name):
                environ['PATH_INFO'] = path_info[len(script_name):]
        return self.app(environ, start_response)


def create_app(config_name='default'):
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    app.wsgi_app = ReverseProxyMiddleware(app.wsgi_app)

    db.init_app(app)

    # Register blueprints
    from app.api import api_bp
    app.register_blueprint(api_bp, url_prefix='/api')

    from app.admin import admin_bp
    app.register_blueprint(admin_bp, url_prefix='/admin')

    from app.review import review_bp
    app.register_blueprint(review_bp, url_prefix='/review')

    # Create tables
    with app.app_context():
        from app import models  # noqa: F401
        db.create_all()

    return app

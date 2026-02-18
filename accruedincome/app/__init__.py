"""Application factory for Accrued Income Calculator."""

import os
from flask import Flask, jsonify
from config import config
from .extensions import db


def create_app(config_name='default'):
    """Create and configure the Flask application."""
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # Ensure folders exist
    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)
    os.makedirs(app.config['CHARTS_FOLDER'], exist_ok=True)

    # Initialize extensions
    db.init_app(app)

    # Portal authentication
    from .portal_auth import init_portal_auth
    init_portal_auth(app)

    # Health check endpoint (used by portal to check if app is online)
    @app.route('/health')
    def health():
        return jsonify({'status': 'ok', 'app': 'accruedincome'})

    # Import models for db.create_all()
    from . import models  # noqa: F401

    # Register blueprints
    from .main import main_bp
    from .upload import upload_bp
    from .calculation import calculation_bp
    from .reports import reports_bp
    from .comparison import comparison_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(upload_bp, url_prefix='/upload')
    app.register_blueprint(calculation_bp, url_prefix='/calculation')
    app.register_blueprint(reports_bp, url_prefix='/reports')
    app.register_blueprint(comparison_bp, url_prefix='/comparison')

    # Create database tables
    with app.app_context():
        db.create_all()

    return app

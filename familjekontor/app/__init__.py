from flask import Flask
from config import config
from app.extensions import db, migrate, login_manager, csrf


def create_app(config_name=None):
    if config_name is None:
        import os
        config_name = os.environ.get('FLASK_ENV', 'default')

    app = Flask(__name__)
    app.config.from_object(config.get(config_name, config['default']))

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Logga in för att fortsätta.'

    # Import models so Alembic sees them
    from app import models  # noqa: F401

    # Register blueprints
    from app.routes.auth import auth_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.companies import companies_bp
    from app.routes.accounting import accounting_bp
    from app.routes.invoices import invoices_bp
    from app.routes.sie import sie_bp
    from app.routes.reports import reports_bp
    from app.routes.admin import admin_bp
    from app.routes.tax import tax_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(companies_bp, url_prefix='/companies')
    app.register_blueprint(accounting_bp, url_prefix='/accounting')
    app.register_blueprint(invoices_bp, url_prefix='/invoices')
    app.register_blueprint(sie_bp, url_prefix='/sie')
    app.register_blueprint(reports_bp, url_prefix='/reports')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(tax_bp, url_prefix='/tax')

    # Context processor for active company
    @app.context_processor
    def inject_active_company():
        from flask import session
        from app.models.company import Company
        active_company = None
        companies = []
        from flask_login import current_user
        if current_user.is_authenticated:
            companies = Company.query.filter_by(active=True).order_by(Company.name).all()
            company_id = session.get('active_company_id')
            if company_id:
                active_company = db.session.get(Company, company_id)
            elif companies:
                active_company = companies[0]
                session['active_company_id'] = active_company.id
        return dict(active_company=active_company, companies=companies)

    return app

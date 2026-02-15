from flask import Flask, render_template, request, jsonify
from config import config
from app.extensions import db, migrate, login_manager, csrf, limiter


def create_app(config_name=None):
    if config_name is None:
        import os
        config_name = os.environ.get('FLASK_ENV', 'default')

    app = Flask(__name__)
    app.config.from_object(config.get(config_name, config['default']))

    if config_name == 'production' and app.config['SECRET_KEY'] == 'dev-secret-key-change-me':
        raise RuntimeError('Set SECRET_KEY environment variable for production')

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    if not app.config.get('RATELIMIT_ENABLED', True):
        limiter.enabled = False
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
    from app.routes.salary import salary_bp
    from app.routes.bank import bank_bp
    from app.routes.budget import budget_bp
    from app.routes.documents import documents_bp
    from app.routes.consolidation import consolidation_bp
    from app.routes.payments import payments_bp
    from app.routes.payment_files import payment_files_bp
    from app.routes.closing import closing_bp
    from app.routes.currency import currency_bp
    from app.routes.recurring import recurring_bp
    from app.routes.annual_report import annual_report_bp
    from app.routes.assets import assets_bp
    from app.routes.governance import governance_bp
    from app.routes.investments import investments_bp
    from app.routes.ai_assistant import ai_bp
    from app.routes.ratios import ratios_bp
    from app.routes.cashflow import cashflow_bp
    from app.routes.comparison import comparison_bp
    from app.routes.arap import arap_bp
    from app.routes.report_center import report_center_bp
    from app.routes.notifications import notification_bp
    from app.routes.batch import batch_bp
    from app.routes.favorites import favorites_bp
    from app.routes.family import family_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(companies_bp, url_prefix='/companies')
    app.register_blueprint(accounting_bp, url_prefix='/accounting')
    app.register_blueprint(invoices_bp, url_prefix='/invoices')
    app.register_blueprint(sie_bp, url_prefix='/sie')
    app.register_blueprint(reports_bp, url_prefix='/reports')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(tax_bp, url_prefix='/tax')
    app.register_blueprint(salary_bp, url_prefix='/salary')
    app.register_blueprint(bank_bp, url_prefix='/bank')
    app.register_blueprint(budget_bp, url_prefix='/budget')
    app.register_blueprint(documents_bp, url_prefix='/documents')
    app.register_blueprint(consolidation_bp, url_prefix='/consolidation')
    app.register_blueprint(payments_bp, url_prefix='/payments')
    app.register_blueprint(payment_files_bp, url_prefix='/payment-files')
    app.register_blueprint(closing_bp, url_prefix='/closing')
    app.register_blueprint(currency_bp, url_prefix='/currency')
    app.register_blueprint(recurring_bp, url_prefix='/invoices/recurring')
    app.register_blueprint(annual_report_bp, url_prefix='/annual-report')
    app.register_blueprint(assets_bp, url_prefix='/assets')
    app.register_blueprint(governance_bp, url_prefix='/governance')
    app.register_blueprint(investments_bp, url_prefix='/investments')
    app.register_blueprint(ai_bp, url_prefix='/ai')
    app.register_blueprint(ratios_bp, url_prefix='/ratios')
    app.register_blueprint(cashflow_bp, url_prefix='/cashflow')
    app.register_blueprint(comparison_bp, url_prefix='/comparison')
    app.register_blueprint(arap_bp, url_prefix='/arap')
    app.register_blueprint(report_center_bp, url_prefix='/report-center')
    app.register_blueprint(notification_bp, url_prefix='/notifications')
    app.register_blueprint(batch_bp, url_prefix='/batch')
    app.register_blueprint(favorites_bp, url_prefix='/favorites')
    app.register_blueprint(family_bp, url_prefix='/family')

    # Jinja2 globals and filters
    from datetime import datetime
    app.jinja_env.globals['now'] = datetime.now

    def format_sek(value, decimals=2):
        """Format number Swedish style: 1 234 567,89"""
        if value is None:
            return '-'
        formatted = f"{value:,.{decimals}f}"
        formatted = formatted.replace(',', '\xa0').replace('.', ',')
        return formatted

    app.jinja_env.filters['sek'] = format_sek

    # Error handlers
    @app.errorhandler(404)
    def not_found(e):
        return render_template('errors/404.html'), 404

    @app.errorhandler(429)
    def ratelimit_handler(e):
        if request.is_json or request.path.startswith('/api/'):
            return jsonify({'error': 'För många förfrågningar'}), 429
        return render_template('errors/429.html'), 429

    @app.errorhandler(500)
    def internal_error(e):
        db.session.rollback()
        return render_template('errors/500.html'), 500

    # Security headers
    @app.after_request
    def set_security_headers(response):
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'

        # Content Security Policy
        csp = '; '.join([
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
            "font-src 'self' https://cdn.jsdelivr.net",
            "img-src 'self' data:",
            "connect-src 'self'",
            "frame-ancestors 'none'",
        ])
        response.headers['Content-Security-Policy'] = csp

        # HSTS — production only
        if not app.debug and not app.testing:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'

        return response

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

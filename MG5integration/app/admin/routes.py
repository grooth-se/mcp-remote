from flask import render_template, redirect, url_for, flash, current_app
from app.admin import admin_bp
from app.extensions import db
from app.models import (
    Account, Verification, Project, ProjectAdjustment, TimeTracking,
    CustomerOrderProjectMap, CustomerOrder, PurchaseOrder, Quote,
    OrderIntake, InvoiceLog, ExchangeRate, Article, MinimumStock,
    ExtractionLog
)
from app.services.import_service import ImportService


@admin_bp.route('/')
def dashboard():
    counts = {
        'accounts': db.session.query(Account).count(),
        'verifications': db.session.query(Verification).count(),
        'projects': db.session.query(Project).count(),
        'project_adjustments': db.session.query(ProjectAdjustment).count(),
        'time_tracking': db.session.query(TimeTracking).count(),
        'co_project_map': db.session.query(CustomerOrderProjectMap).count(),
        'customer_orders': db.session.query(CustomerOrder).count(),
        'purchase_orders': db.session.query(PurchaseOrder).count(),
        'quotes': db.session.query(Quote).count(),
        'order_intake': db.session.query(OrderIntake).count(),
        'invoice_log': db.session.query(InvoiceLog).count(),
        'exchange_rates': db.session.query(ExchangeRate).count(),
        'articles': db.session.query(Article).count(),
        'minimum_stock': db.session.query(MinimumStock).count(),
    }
    last_extraction = db.session.query(ExtractionLog).order_by(
        ExtractionLog.started_at.desc()
    ).first()
    return render_template(
        'dashboard.html',
        counts=counts,
        last_extraction=last_extraction,
        total=sum(counts.values())
    )


@admin_bp.route('/import', methods=['POST'])
def run_import():
    folder = current_app.config['EXCEL_EXPORTS_FOLDER']
    service = ImportService()
    log = service.run_full_import(folder)
    if log.status == 'success':
        flash(f'Import completed: {log.records_imported} records imported.', 'success')
    else:
        flash(f'Import completed with errors: {log.errors}', 'warning')
    return redirect(url_for('admin.dashboard'))

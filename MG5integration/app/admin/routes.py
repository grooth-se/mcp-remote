import os
from datetime import datetime, timezone
from pathlib import Path

from flask import render_template, redirect, url_for, flash, current_app, request
from werkzeug.utils import secure_filename
from app.admin import admin_bp
from app.extensions import db
from app.models import (
    Account, Verification, Project, ProjectAdjustment, TimeTracking,
    CustomerOrderProjectMap, CustomerOrder, PurchaseOrder, Quote,
    OrderIntake, InvoiceLog, ExchangeRate, Article, MinimumStock,
    ExtractionLog
)
from app.services.import_service import ImportService, EXTRACTOR_REGISTRY
from app.utils.excel_analyzer import (
    UPLOAD_TABLE_INFO, FILE_PATTERN_MAP, find_file_for_key,
)


# Map dashboard count keys to extractor keys
COUNTS_TO_EXTRACTOR_KEY = {
    'accounts': 'kontoplan',
    'verifications': 'verlista',
    'projects': 'projektuppf',
    'project_adjustments': 'projectadjustments',
    'time_tracking': 'tiduppfoljning',
    'co_project_map': 'CO_proj_crossref',
    'customer_orders': 'kundorderforteckning',
    'purchase_orders': 'inkoporderforteckning',
    'quotes': 'offertforteckning',
    'order_intake': 'orderingang',
    'invoice_log': 'faktureringslogg',
    'exchange_rates': 'valutakurser',
    'articles': 'artikellista',
    'minimum_stock': 'min_stock',
}


def _get_file_status(folder):
    """Return dict of extractor_key -> {exists, modified} for each table."""
    status = {}
    for key in UPLOAD_TABLE_INFO:
        found = find_file_for_key(folder, key)
        if found and found.exists():
            mtime = datetime.fromtimestamp(found.stat().st_mtime, tz=timezone.utc)
            status[key] = {'exists': True, 'modified': mtime.strftime('%Y-%m-%d %H:%M')}
        else:
            status[key] = {'exists': False, 'modified': None}
    return status


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

    folder = current_app.config['EXCEL_EXPORTS_FOLDER']
    file_status = _get_file_status(folder)

    return render_template(
        'dashboard.html',
        counts=counts,
        last_extraction=last_extraction,
        total=sum(counts.values()),
        file_status=file_status,
        upload_info=UPLOAD_TABLE_INFO,
        counts_to_key=COUNTS_TO_EXTRACTOR_KEY,
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


@admin_bp.route('/upload', methods=['POST'])
def upload_single():
    """Upload a single Excel file for a specific table."""
    table_key = request.form.get('table_key', '')
    valid_keys = {k for k, _ in EXTRACTOR_REGISTRY}

    if table_key not in valid_keys:
        flash(f'Invalid table key: {table_key}', 'danger')
        return redirect(url_for('admin.dashboard'))

    file = request.files.get('file')
    if not file or file.filename == '':
        flash('No file selected.', 'warning')
        return redirect(url_for('admin.dashboard'))

    if not file.filename.lower().endswith('.xlsx'):
        flash('Only .xlsx files are accepted.', 'danger')
        return redirect(url_for('admin.dashboard'))

    folder = current_app.config['EXCEL_EXPORTS_FOLDER']
    os.makedirs(folder, exist_ok=True)

    # Save with canonical filename so find_file_for_key() can locate it
    canonical = UPLOAD_TABLE_INFO[table_key]['canonical_filename']
    dest = os.path.join(folder, canonical)
    file.save(dest)

    service = ImportService()
    result = service.run_single_import(table_key, dest)

    if result['status'] == 'success':
        flash(f'{UPLOAD_TABLE_INFO[table_key]["label"]}: {result["records"]} records imported.', 'success')
    else:
        flash(f'{UPLOAD_TABLE_INFO[table_key]["label"]}: {result["error"]}', 'danger')

    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/upload-multiple', methods=['POST'])
def upload_multiple():
    """Upload multiple Excel files with auto-detection by filename."""
    files = request.files.getlist('files')
    if not files or all(f.filename == '' for f in files):
        flash('No files selected.', 'warning')
        return redirect(url_for('admin.dashboard'))

    folder = current_app.config['EXCEL_EXPORTS_FOLDER']
    os.makedirs(folder, exist_ok=True)

    results = []
    for file in files:
        if not file.filename or file.filename == '':
            continue
        if not file.filename.lower().endswith('.xlsx'):
            results.append(f'{file.filename}: rejected (not .xlsx)')
            continue

        # Auto-detect table key from filename
        detected_key = None
        for pattern, key in FILE_PATTERN_MAP.items():
            if pattern.lower() in file.filename.lower():
                detected_key = key
                break

        if detected_key is None:
            results.append(f'{file.filename}: unrecognized filename')
            continue

        canonical = UPLOAD_TABLE_INFO[detected_key]['canonical_filename']
        dest = os.path.join(folder, canonical)
        file.save(dest)

        service = ImportService()
        result = service.run_single_import(detected_key, dest)

        label = UPLOAD_TABLE_INFO[detected_key]['label']
        if result['status'] == 'success':
            results.append(f'{label}: {result["records"]} records imported')
        else:
            results.append(f'{label}: {result["error"]}')

    if results:
        flash(' | '.join(results), 'info')
    else:
        flash('No valid files were uploaded.', 'warning')

    return redirect(url_for('admin.dashboard'))

"""Batch operations routes (Phase 7C)."""

from flask import (
    Blueprint, session, redirect, url_for, flash, request, send_file,
)
from flask_login import login_required, current_user

from app.services.batch_service import (
    batch_approve_supplier_invoices, batch_delete_verifications,
    batch_delete_documents, batch_export_verifications,
    batch_export_supplier_invoices, batch_export_customer_invoices,
    batch_export_documents,
)

batch_bp = Blueprint('batch', __name__)


def _parse_ids():
    """Parse comma-separated IDs from form data."""
    raw = request.form.get('ids', '')
    ids = []
    for part in raw.split(','):
        part = part.strip()
        if part.isdigit():
            ids.append(int(part))
    return ids


def _get_company():
    company_id = session.get('active_company_id')
    if not company_id:
        return None
    return company_id


# --- Verifications ---

@batch_bp.route('/verifications/delete', methods=['POST'])
@login_required
def delete_verifications():
    company_id = _get_company()
    if not company_id:
        return redirect(url_for('dashboard.index'))
    if current_user.is_readonly:
        flash('Skrivskyddad användare kan inte ta bort.', 'danger')
        return redirect(url_for('accounting.index'))

    ids = _parse_ids()
    if not ids:
        flash('Inga verifikationer markerade.', 'warning')
        return redirect(url_for('accounting.index'))

    result = batch_delete_verifications(ids, company_id, current_user.id)
    flash(f'{result["deleted"]} verifikationer borttagna.', 'success')
    for err in result['errors']:
        flash(err, 'warning')
    return redirect(url_for('accounting.index'))


@batch_bp.route('/verifications/export', methods=['POST'])
@login_required
def export_verifications():
    company_id = _get_company()
    if not company_id:
        return redirect(url_for('dashboard.index'))
    ids = _parse_ids()
    if not ids:
        flash('Inga verifikationer markerade.', 'warning')
        return redirect(url_for('accounting.index'))
    output = batch_export_verifications(ids, company_id)
    return send_file(output, mimetype='text/csv',
                     as_attachment=True, download_name='verifikationer_urval.csv')


# --- Supplier invoices ---

@batch_bp.route('/supplier-invoices/approve', methods=['POST'])
@login_required
def approve_supplier_invoices():
    company_id = _get_company()
    if not company_id:
        return redirect(url_for('dashboard.index'))
    if current_user.is_readonly:
        flash('Skrivskyddad användare kan inte godkänna.', 'danger')
        return redirect(url_for('invoices.supplier_invoices'))

    ids = _parse_ids()
    if not ids:
        flash('Inga fakturor markerade.', 'warning')
        return redirect(url_for('invoices.supplier_invoices'))

    result = batch_approve_supplier_invoices(ids, company_id, current_user.id)
    flash(f'{result["approved"]} fakturor godkända.', 'success')
    for err in result['errors']:
        flash(err, 'warning')
    return redirect(url_for('invoices.supplier_invoices'))


@batch_bp.route('/supplier-invoices/export', methods=['POST'])
@login_required
def export_supplier_invoices():
    company_id = _get_company()
    if not company_id:
        return redirect(url_for('dashboard.index'))
    ids = _parse_ids()
    if not ids:
        flash('Inga fakturor markerade.', 'warning')
        return redirect(url_for('invoices.supplier_invoices'))
    output = batch_export_supplier_invoices(ids, company_id)
    return send_file(output, mimetype='text/csv',
                     as_attachment=True, download_name='leverantorsfakturor_urval.csv')


# --- Customer invoices ---

@batch_bp.route('/customer-invoices/export', methods=['POST'])
@login_required
def export_customer_invoices():
    company_id = _get_company()
    if not company_id:
        return redirect(url_for('dashboard.index'))
    ids = _parse_ids()
    if not ids:
        flash('Inga fakturor markerade.', 'warning')
        return redirect(url_for('invoices.customer_invoices'))
    output = batch_export_customer_invoices(ids, company_id)
    return send_file(output, mimetype='text/csv',
                     as_attachment=True, download_name='kundfakturor_urval.csv')


# --- Documents ---

@batch_bp.route('/documents/delete', methods=['POST'])
@login_required
def delete_documents():
    company_id = _get_company()
    if not company_id:
        return redirect(url_for('dashboard.index'))
    if current_user.is_readonly:
        flash('Skrivskyddad användare kan inte ta bort.', 'danger')
        return redirect(url_for('documents.index'))

    ids = _parse_ids()
    if not ids:
        flash('Inga dokument markerade.', 'warning')
        return redirect(url_for('documents.index'))

    result = batch_delete_documents(ids, company_id, current_user.id)
    flash(f'{result["deleted"]} dokument borttagna.', 'success')
    for err in result['errors']:
        flash(err, 'warning')
    return redirect(url_for('documents.index'))


@batch_bp.route('/documents/export', methods=['POST'])
@login_required
def export_documents():
    company_id = _get_company()
    if not company_id:
        return redirect(url_for('dashboard.index'))
    ids = _parse_ids()
    if not ids:
        flash('Inga dokument markerade.', 'warning')
        return redirect(url_for('documents.index'))
    output = batch_export_documents(ids, company_id)
    return send_file(output, mimetype='text/csv',
                     as_attachment=True, download_name='dokument_urval.csv')

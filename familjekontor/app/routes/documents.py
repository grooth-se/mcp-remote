from datetime import date, datetime
from flask import (Blueprint, render_template, redirect, url_for, flash,
                   request, session, send_file, jsonify)
from flask_login import login_required, current_user
from app.extensions import db
from app.models.document import Document
from app.models.accounting import Verification
from app.forms.document import DocumentUploadForm, DocumentFilterForm
from app.services import document_service

documents_bp = Blueprint('documents', __name__)


def _get_company_id():
    return session.get('active_company_id')


@documents_bp.route('/')
@login_required
def index():
    company_id = _get_company_id()
    if not company_id:
        flash('Välj ett företag först.', 'warning')
        return redirect(url_for('companies.index'))

    form = DocumentFilterForm(request.args, meta={'csrf': False})
    doc_type = request.args.get('doc_type', '')
    if doc_type and doc_type not in ('faktura', 'avtal', 'intyg', 'certificate', 'arsredovisning', 'kvitto', 'ovrigt'):
        doc_type = ''
    search = request.args.get('search', '')
    page = request.args.get('page', 1, type=int)

    pagination = document_service.get_documents(
        company_id, doc_type=doc_type or None, search=search or None, page=page,
        exclude_accounting=True
    )

    return render_template('documents/index.html',
                           form=form, pagination=pagination,
                           doc_type=doc_type, search=search,
                           today=date.today())


@documents_bp.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    company_id = _get_company_id()
    if not company_id:
        return redirect(url_for('companies.index'))

    form = DocumentUploadForm()
    if form.validate_on_submit():
        doc, error = document_service.upload_document(
            company_id=company_id,
            file=form.file.data,
            doc_type=form.document_type.data,
            description=form.description.data,
            valid_from=form.valid_from.data,
            expiry_date=form.expiry_date.data,
            user_id=current_user.id,
        )
        if doc:
            flash(f'Dokument "{doc.file_name}" har laddats upp.', 'success')
            return redirect(url_for('documents.view', doc_id=doc.id))
        else:
            flash(error or 'Uppladdningen misslyckades.', 'danger')

    return render_template('documents/upload.html', form=form)


@documents_bp.route('/api/analyze', methods=['POST'])
@login_required
def api_analyze():
    """Analyze an uploaded file and return metadata suggestions."""
    company_id = _get_company_id()
    if not company_id:
        return jsonify({'error': 'Inget företag valt'}), 400

    file = request.files.get('file')
    if not file:
        return jsonify({'error': 'Ingen fil'}), 400

    result = document_service.analyze_file(file)
    return jsonify(result)


@documents_bp.route('/api/upload', methods=['POST'])
@login_required
def api_upload():
    """AJAX drag-and-drop upload endpoint."""
    company_id = _get_company_id()
    if not company_id:
        return jsonify({'error': 'Inget företag valt'}), 400

    file = request.files.get('file')
    if not file:
        return jsonify({'error': 'Ingen fil'}), 400

    doc_type = request.form.get('document_type', 'ovrigt')
    description = request.form.get('description', '')

    # Parse dates from form data
    valid_from = None
    expiry_date = None
    valid_from_str = request.form.get('valid_from', '')
    expiry_date_str = request.form.get('expiry_date', '')
    if valid_from_str:
        try:
            valid_from = datetime.strptime(valid_from_str, '%Y-%m-%d').date()
        except ValueError:
            pass
    if expiry_date_str:
        try:
            expiry_date = datetime.strptime(expiry_date_str, '%Y-%m-%d').date()
        except ValueError:
            pass

    doc, error = document_service.upload_document(
        company_id=company_id,
        file=file,
        doc_type=doc_type,
        description=description,
        valid_from=valid_from,
        expiry_date=expiry_date,
        user_id=current_user.id,
    )

    if doc:
        return jsonify({
            'success': True,
            'id': doc.id,
            'file_name': doc.file_name,
            'url': url_for('documents.view', doc_id=doc.id),
        })
    else:
        return jsonify({'error': error}), 400


@documents_bp.route('/<int:doc_id>')
@login_required
def view(doc_id):
    company_id = _get_company_id()
    doc = db.session.get(Document, doc_id)
    if not doc or doc.company_id != company_id:
        flash('Dokument hittades inte.', 'danger')
        return redirect(url_for('documents.index'))

    return render_template('documents/view.html', doc=doc)


@documents_bp.route('/<int:doc_id>/download')
@login_required
def download(doc_id):
    company_id = _get_company_id()
    doc = db.session.get(Document, doc_id)
    if not doc or doc.company_id != company_id:
        flash('Dokument hittades inte.', 'danger')
        return redirect(url_for('documents.index'))
    path, mime = document_service.get_document_file_path(doc_id)
    if not path:
        flash('Fil hittades inte.', 'danger')
        return redirect(url_for('documents.index'))
    return send_file(path, as_attachment=True, mimetype=mime)


@documents_bp.route('/<int:doc_id>/preview')
@login_required
def preview(doc_id):
    company_id = _get_company_id()
    doc = db.session.get(Document, doc_id)
    if not doc or doc.company_id != company_id:
        flash('Dokument hittades inte.', 'danger')
        return redirect(url_for('documents.index'))
    path, mime = document_service.get_document_file_path(doc_id)
    if not path:
        flash('Fil hittades inte.', 'danger')
        return redirect(url_for('documents.index'))
    return send_file(path, mimetype=mime)


@documents_bp.route('/<int:doc_id>/attach-verification', methods=['POST'])
@login_required
def attach_verification(doc_id):
    company_id = _get_company_id()
    doc = db.session.get(Document, doc_id)
    if not doc or doc.company_id != company_id:
        flash('Dokument hittades inte.', 'danger')
        return redirect(url_for('documents.index'))
    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('documents.view', doc_id=doc_id))
    verification_id = request.form.get('verification_id', type=int)
    if verification_id:
        document_service.attach_to_verification(doc_id, verification_id, current_user.id)
        flash('Dokument kopplat till verifikation.', 'success')
    return redirect(url_for('documents.view', doc_id=doc_id))


@documents_bp.route('/<int:doc_id>/attach-invoice', methods=['POST'])
@login_required
def attach_invoice(doc_id):
    company_id = _get_company_id()
    doc = db.session.get(Document, doc_id)
    if not doc or doc.company_id != company_id:
        flash('Dokument hittades inte.', 'danger')
        return redirect(url_for('documents.index'))
    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('documents.view', doc_id=doc_id))
    invoice_id = request.form.get('invoice_id', type=int)
    invoice_type = request.form.get('invoice_type', 'supplier')
    if invoice_id:
        document_service.attach_to_invoice(doc_id, invoice_id, invoice_type, current_user.id)
        flash('Dokument kopplat till faktura.', 'success')
    return redirect(url_for('documents.view', doc_id=doc_id))


@documents_bp.route('/<int:doc_id>/detach', methods=['POST'])
@login_required
def detach(doc_id):
    company_id = _get_company_id()
    doc = db.session.get(Document, doc_id)
    if not doc or doc.company_id != company_id:
        flash('Dokument hittades inte.', 'danger')
        return redirect(url_for('documents.index'))
    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('documents.view', doc_id=doc_id))
    document_service.detach_document(doc_id, current_user.id)
    flash('Koppling borttagen.', 'success')
    return redirect(url_for('documents.view', doc_id=doc_id))


@documents_bp.route('/<int:doc_id>/delete', methods=['POST'])
@login_required
def delete(doc_id):
    company_id = _get_company_id()
    doc = db.session.get(Document, doc_id)
    if not doc or doc.company_id != company_id:
        flash('Dokument hittades inte.', 'danger')
        return redirect(url_for('documents.index'))
    if current_user.is_readonly:
        flash('Du har inte behörighet.', 'danger')
        return redirect(url_for('documents.view', doc_id=doc_id))
    document_service.delete_document(doc_id, current_user.id)
    flash('Dokument har tagits bort.', 'success')
    return redirect(url_for('documents.index'))

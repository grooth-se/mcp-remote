"""Document management service: upload, attach, browse, preview."""

import os
import uuid
from datetime import datetime, timezone
from werkzeug.utils import secure_filename

from flask import current_app
from app.extensions import db
from app.models.document import Document
from app.models.audit import AuditLog


ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'gif', 'doc', 'docx', 'xls', 'xlsx', 'csv', 'txt'}


def _allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _get_upload_dir(company_id):
    upload_dir = os.path.join(current_app.static_folder, 'uploads', str(company_id))
    os.makedirs(upload_dir, exist_ok=True)
    return upload_dir


def upload_document(company_id, file, doc_type, description=None, expiry_date=None,
                    verification_id=None, invoice_id=None, customer_invoice_id=None,
                    user_id=None):
    """Upload and store a document file."""
    if not file or not _allowed_file(file.filename):
        return None, 'Ogiltig filtyp.'

    original_name = secure_filename(file.filename)
    ext = original_name.rsplit('.', 1)[1].lower()
    unique_name = f'{uuid.uuid4().hex[:12]}_{original_name}'

    upload_dir = _get_upload_dir(company_id)
    file_path = os.path.join(upload_dir, unique_name)
    file.save(file_path)

    # Determine MIME type
    mime_map = {
        'pdf': 'application/pdf',
        'png': 'image/png', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'gif': 'image/gif',
        'doc': 'application/msword',
        'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'xls': 'application/vnd.ms-excel',
        'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'csv': 'text/csv', 'txt': 'text/plain',
    }

    relative_path = f'uploads/{company_id}/{unique_name}'

    doc = Document(
        company_id=company_id,
        document_type=doc_type,
        file_name=original_name,
        file_path=relative_path,
        mime_type=mime_map.get(ext, 'application/octet-stream'),
        description=description,
        expiry_date=expiry_date,
        uploaded_by=user_id,
        verification_id=verification_id,
        invoice_id=invoice_id,
        customer_invoice_id=customer_invoice_id,
    )
    db.session.add(doc)

    if user_id:
        audit = AuditLog(
            company_id=company_id, user_id=user_id,
            action='create', entity_type='document', entity_id=0,
            new_values={'file_name': original_name, 'type': doc_type},
        )
        db.session.add(audit)

    db.session.commit()

    # Update audit with real ID
    if user_id:
        audit.entity_id = doc.id
        db.session.commit()

    return doc, None


def get_documents(company_id, doc_type=None, search=None, page=1, per_page=25):
    """Get paginated document list with optional filters."""
    query = Document.query.filter_by(company_id=company_id)

    if doc_type:
        query = query.filter_by(document_type=doc_type)
    if search:
        query = query.filter(
            Document.file_name.ilike(f'%{search}%') |
            Document.description.ilike(f'%{search}%')
        )

    return query.order_by(Document.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )


def attach_to_verification(doc_id, verification_id, user_id):
    doc = db.session.get(Document, doc_id)
    if not doc:
        return False
    doc.verification_id = verification_id
    audit = AuditLog(
        company_id=doc.company_id, user_id=user_id,
        action='update', entity_type='document', entity_id=doc.id,
        new_values={'verification_id': verification_id},
    )
    db.session.add(audit)
    db.session.commit()
    return True


def attach_to_invoice(doc_id, invoice_id, invoice_type, user_id):
    doc = db.session.get(Document, doc_id)
    if not doc:
        return False

    if invoice_type == 'supplier':
        doc.invoice_id = invoice_id
    elif invoice_type == 'customer':
        doc.customer_invoice_id = invoice_id

    audit = AuditLog(
        company_id=doc.company_id, user_id=user_id,
        action='update', entity_type='document', entity_id=doc.id,
        new_values={f'{invoice_type}_invoice_id': invoice_id},
    )
    db.session.add(audit)
    db.session.commit()
    return True


def detach_document(doc_id, user_id):
    doc = db.session.get(Document, doc_id)
    if not doc:
        return False

    doc.verification_id = None
    doc.invoice_id = None
    doc.customer_invoice_id = None

    audit = AuditLog(
        company_id=doc.company_id, user_id=user_id,
        action='update', entity_type='document', entity_id=doc.id,
        new_values={'detached': True},
    )
    db.session.add(audit)
    db.session.commit()
    return True


def delete_document(doc_id, user_id):
    doc = db.session.get(Document, doc_id)
    if not doc:
        return False

    # Delete file from disk
    if doc.file_path:
        full_path = os.path.join(current_app.static_folder, doc.file_path)
        if os.path.exists(full_path):
            os.remove(full_path)

    audit = AuditLog(
        company_id=doc.company_id, user_id=user_id,
        action='delete', entity_type='document', entity_id=doc.id,
        old_values={'file_name': doc.file_name},
    )
    db.session.add(audit)
    db.session.delete(doc)
    db.session.commit()
    return True


def get_document_file_path(doc_id):
    doc = db.session.get(Document, doc_id)
    if not doc or not doc.file_path:
        return None, None
    full_path = os.path.join(current_app.static_folder, doc.file_path)
    return full_path, doc.mime_type

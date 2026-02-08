"""Document management service: upload, attach, browse, preview, analyze."""

import os
import re
import uuid
from datetime import datetime, timezone
from werkzeug.utils import secure_filename

from flask import current_app
from app.extensions import db
from app.models.document import Document
from app.models.audit import AuditLog


ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'gif', 'doc', 'docx', 'xls', 'xlsx', 'csv', 'txt'}

# Keywords mapped to document types
TYPE_KEYWORDS = {
    'faktura': ['faktura', 'invoice', 'fakturanr', 'fakturanummer'],
    'avtal': ['avtal', 'kontrakt', 'agreement', 'contract'],
    'intyg': ['intyg', 'certifikat', 'certificate', 'attestation'],
    'certificate': ['registreringsbevis', 'bolagsverket', 'registration',
                     'f-skatt', 'moms-registrering', 'organisationsnummer'],
    'arsredovisning': ['årsredovisning', 'arsredovisning', 'annual report',
                        'balansräkning', 'resultaträkning'],
    'kvitto': ['kvitto', 'receipt', 'betalning', 'payment'],
}

# Date patterns: YYYY-MM-DD, DD/MM/YYYY, DD.MM.YYYY, DD-MM-YYYY
DATE_PATTERNS = [
    (r'(\d{4})-(\d{2})-(\d{2})', lambda m: f'{m.group(1)}-{m.group(2)}-{m.group(3)}'),
    (r'(\d{2})/(\d{2})/(\d{4})', lambda m: f'{m.group(3)}-{m.group(2)}-{m.group(1)}'),
    (r'(\d{2})\.(\d{2})\.(\d{4})', lambda m: f'{m.group(3)}-{m.group(2)}-{m.group(1)}'),
    (r'(\d{2})-(\d{2})-(\d{4})', lambda m: f'{m.group(3)}-{m.group(2)}-{m.group(1)}'),
]

# Keywords that suggest a date is "valid from" vs "valid to"
VALID_FROM_KEYWORDS = ['från', 'from', 'giltig från', 'gäller från', 'utfärdad', 'issued', 'datum']
VALID_TO_KEYWORDS = ['till', 'to', 'giltig till', 'gäller till', 'utgår', 'expires', 'förfaller']


def _allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _get_upload_dir(company_id):
    upload_dir = os.path.join(current_app.static_folder, 'uploads', str(company_id))
    os.makedirs(upload_dir, exist_ok=True)
    return upload_dir


def _extract_dates(text):
    """Extract dates from text, returning list of (date_str, context) tuples."""
    dates = []
    for pattern, formatter in DATE_PATTERNS:
        for match in re.finditer(pattern, text):
            date_str = formatter(match)
            try:
                datetime.strptime(date_str, '%Y-%m-%d')
                # Get surrounding context (50 chars before and after)
                start = max(0, match.start() - 50)
                end = min(len(text), match.end() + 50)
                context = text[start:end].lower()
                dates.append((date_str, context))
            except ValueError:
                continue
    return dates


def _guess_type_from_text(text):
    """Guess document type from text content."""
    text_lower = text.lower()
    scores = {}
    for doc_type, keywords in TYPE_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > 0:
            scores[doc_type] = score
    if scores:
        return max(scores, key=scores.get)
    return None


def _extract_description(text, max_length=200):
    """Extract a short description from text (first meaningful line)."""
    for line in text.split('\n'):
        line = line.strip()
        if len(line) > 10 and not line.startswith(('http', 'www', '//')):
            return line[:max_length]
    return None


def analyze_file(file_storage):
    """Analyze an uploaded file and return metadata suggestions.

    Args:
        file_storage: werkzeug FileStorage object

    Returns:
        dict with suggested_type, suggested_description, suggested_valid_from, suggested_expiry_date
    """
    result = {
        'suggested_type': None,
        'suggested_description': None,
        'suggested_valid_from': None,
        'suggested_expiry_date': None,
    }

    filename = file_storage.filename or ''
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''

    # Analyze filename — extract dates before replacing dashes
    filename_dates = _extract_dates(filename)
    filename_text = filename.replace('_', ' ').replace('-', ' ')
    filename_type = _guess_type_from_text(filename_text)
    if filename_type:
        result['suggested_type'] = filename_type

    if filename_dates:
        result['suggested_valid_from'] = filename_dates[0][0]
        if len(filename_dates) > 1:
            result['suggested_expiry_date'] = filename_dates[1][0]

    # For PDFs, extract text with pdfplumber
    if ext == 'pdf':
        try:
            import pdfplumber
            file_storage.seek(0)
            with pdfplumber.open(file_storage) as pdf:
                text = ''
                for page in pdf.pages[:2]:  # First 2 pages max
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + '\n'

            file_storage.seek(0)  # Reset for later use

            if text.strip():
                # Type from PDF text (override filename guess if found)
                pdf_type = _guess_type_from_text(text)
                if pdf_type:
                    result['suggested_type'] = pdf_type

                # Description from PDF
                desc = _extract_description(text)
                if desc:
                    result['suggested_description'] = desc

                # Dates from PDF
                dates = _extract_dates(text)
                if dates:
                    valid_from = None
                    valid_to = None
                    for date_str, context in dates:
                        if any(kw in context for kw in VALID_TO_KEYWORDS):
                            if not valid_to:
                                valid_to = date_str
                        elif any(kw in context for kw in VALID_FROM_KEYWORDS):
                            if not valid_from:
                                valid_from = date_str
                        else:
                            if not valid_from:
                                valid_from = date_str
                            elif not valid_to:
                                valid_to = date_str

                    if valid_from:
                        result['suggested_valid_from'] = valid_from
                    if valid_to:
                        result['suggested_expiry_date'] = valid_to

        except Exception:
            pass  # PDF analysis is best-effort

    # Default type if nothing found
    if not result['suggested_type']:
        result['suggested_type'] = 'ovrigt'

    return result


def upload_document(company_id, file, doc_type, description=None,
                    valid_from=None, expiry_date=None,
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
        valid_from=valid_from,
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


def get_documents(company_id, doc_type=None, search=None, page=1, per_page=25,
                  exclude_accounting=True):
    """Get paginated document list with optional filters.

    Args:
        exclude_accounting: If True, exclude docs linked to verifications/invoices.
    """
    query = Document.query.filter_by(company_id=company_id)

    if exclude_accounting:
        query = query.filter(
            Document.verification_id.is_(None),
            Document.invoice_id.is_(None),
            Document.customer_invoice_id.is_(None),
        )

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

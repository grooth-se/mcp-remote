"""Batch operations service (Phase 7C)."""

from flask_login import current_user

from app.extensions import db
from app.models.accounting import Verification, VerificationRow
from app.models.invoice import SupplierInvoice, CustomerInvoice
from app.models.document import Document
from app.models.audit import AuditLog
from app.services.csv_export_service import export_csv


def batch_approve_supplier_invoices(ids, company_id, user_id):
    """Approve multiple supplier invoices. Returns {approved, errors}."""
    approved = 0
    errors = []
    for inv_id in ids:
        inv = db.session.get(SupplierInvoice, inv_id)
        if not inv or inv.company_id != company_id:
            errors.append(f'Faktura {inv_id} hittades inte')
            continue
        if inv.status == 'approved':
            continue  # already approved, skip silently
        if inv.status != 'pending':
            errors.append(f'Faktura {inv.invoice_number or inv_id} har status {inv.status}')
            continue
        inv.status = 'approved'
        db.session.add(AuditLog(
            user_id=user_id, company_id=company_id,
            entity_type='supplier_invoice', entity_id=inv.id,
            action='approve', new_values=f'Batch-godkänd',
        ))
        approved += 1
    db.session.commit()
    return {'approved': approved, 'errors': errors}


def batch_delete_verifications(ids, company_id, user_id):
    """Delete multiple verifications. Returns {deleted, errors}."""
    deleted = 0
    errors = []
    for ver_id in ids:
        ver = db.session.get(Verification, ver_id)
        if not ver or ver.company_id != company_id:
            errors.append(f'Verifikation {ver_id} hittades inte')
            continue
        # Delete rows first
        VerificationRow.query.filter_by(verification_id=ver.id).delete()
        db.session.add(AuditLog(
            user_id=user_id, company_id=company_id,
            entity_type='verification', entity_id=ver.id,
            action='delete', old_values=f'#{ver.verification_number} {ver.description}',
        ))
        db.session.delete(ver)
        deleted += 1
    db.session.commit()
    return {'deleted': deleted, 'errors': errors}


def batch_delete_documents(ids, company_id, user_id):
    """Delete multiple documents. Returns {deleted, errors}."""
    deleted = 0
    errors = []
    for doc_id in ids:
        doc = db.session.get(Document, doc_id)
        if not doc or doc.company_id != company_id:
            errors.append(f'Dokument {doc_id} hittades inte')
            continue
        db.session.add(AuditLog(
            user_id=user_id, company_id=company_id,
            entity_type='document', entity_id=doc.id,
            action='delete', old_values=doc.file_name or str(doc.id),
        ))
        db.session.delete(doc)
        deleted += 1
    db.session.commit()
    return {'deleted': deleted, 'errors': errors}


def batch_export_verifications(ids, company_id):
    """Export selected verifications to CSV."""
    vers = Verification.query.filter(
        Verification.id.in_(ids),
        Verification.company_id == company_id,
    ).order_by(Verification.verification_number).all()

    rows = [
        {
            'number': v.verification_number,
            'date': v.verification_date,
            'description': v.description or '',
            'type': v.verification_type or '',
            'debit': v.total_debit,
            'credit': v.total_credit,
        }
        for v in vers
    ]
    columns = [
        ('number', 'Nummer'),
        ('date', 'Datum'),
        ('description', 'Beskrivning'),
        ('type', 'Typ'),
        ('debit', 'Debet'),
        ('credit', 'Kredit'),
    ]
    return export_csv(rows, columns)


def batch_export_supplier_invoices(ids, company_id):
    """Export selected supplier invoices to CSV."""
    invs = SupplierInvoice.query.filter(
        SupplierInvoice.id.in_(ids),
        SupplierInvoice.company_id == company_id,
    ).order_by(SupplierInvoice.invoice_date).all()

    rows = [
        {
            'number': inv.invoice_number or '',
            'supplier': inv.supplier.name if inv.supplier else '',
            'date': inv.invoice_date,
            'due_date': inv.due_date,
            'amount': inv.total_amount,
            'status': inv.status,
        }
        for inv in invs
    ]
    columns = [
        ('number', 'Fakturanummer'),
        ('supplier', 'Leverantör'),
        ('date', 'Fakturadatum'),
        ('due_date', 'Förfallodatum'),
        ('amount', 'Belopp'),
        ('status', 'Status'),
    ]
    return export_csv(rows, columns)


def batch_export_customer_invoices(ids, company_id):
    """Export selected customer invoices to CSV."""
    invs = CustomerInvoice.query.filter(
        CustomerInvoice.id.in_(ids),
        CustomerInvoice.company_id == company_id,
    ).order_by(CustomerInvoice.invoice_date).all()

    rows = [
        {
            'number': inv.invoice_number or '',
            'customer': inv.customer.name if inv.customer else '',
            'date': inv.invoice_date,
            'due_date': inv.due_date,
            'amount': inv.total_amount,
            'status': inv.status,
        }
        for inv in invs
    ]
    columns = [
        ('number', 'Fakturanummer'),
        ('customer', 'Kund'),
        ('date', 'Fakturadatum'),
        ('due_date', 'Förfallodatum'),
        ('amount', 'Belopp'),
        ('status', 'Status'),
    ]
    return export_csv(rows, columns)


def batch_export_documents(ids, company_id):
    """Export selected documents metadata to CSV."""
    docs = Document.query.filter(
        Document.id.in_(ids),
        Document.company_id == company_id,
    ).order_by(Document.created_at).all()

    rows = [
        {
            'file_name': d.file_name or '',
            'type': d.document_type or '',
            'description': d.description or '',
            'created': d.created_at.strftime('%Y-%m-%d') if d.created_at else '',
            'expiry': d.expiry_date or '',
        }
        for d in docs
    ]
    columns = [
        ('file_name', 'Filnamn'),
        ('type', 'Dokumenttyp'),
        ('description', 'Beskrivning'),
        ('created', 'Skapad'),
        ('expiry', 'Upphör'),
    ]
    return export_csv(rows, columns)

"""Global search service (Phase 7A)."""

from flask import url_for
from sqlalchemy import cast, String

from app.extensions import db
from app.models.accounting import Verification, Account
from app.models.invoice import Supplier, SupplierInvoice, Customer, CustomerInvoice
from app.models.document import Document
from app.models.salary import Employee


def global_search(company_id, query, limit=5):
    """Search across multiple entity types.

    Returns dict with keys per entity type, each a list of
    {id, title, subtitle, url, icon}.
    """
    if not query or len(query) < 2:
        return {}

    pattern = f'%{query}%'
    results = {}

    # Verifications
    vers = (
        Verification.query
        .filter(Verification.company_id == company_id)
        .filter(
            db.or_(
                cast(Verification.verification_number, String).ilike(pattern),
                Verification.description.ilike(pattern),
            )
        )
        .order_by(Verification.verification_date.desc())
        .limit(limit)
        .all()
    )
    if vers:
        results['verifications'] = [
            {
                'id': v.id,
                'title': f'#{v.verification_number}',
                'subtitle': v.description or '',
                'url': url_for('accounting.view_verification',
                               verification_id=v.id),
                'icon': 'bi-journal-check',
            }
            for v in vers
        ]

    # Supplier invoices — link to list (no detail page)
    si = (
        SupplierInvoice.query
        .join(Supplier, SupplierInvoice.supplier_id == Supplier.id)
        .filter(SupplierInvoice.company_id == company_id)
        .filter(
            db.or_(
                SupplierInvoice.invoice_number.ilike(pattern),
                Supplier.name.ilike(pattern),
            )
        )
        .order_by(SupplierInvoice.invoice_date.desc())
        .limit(limit)
        .all()
    )
    if si:
        results['supplier_invoices'] = [
            {
                'id': inv.id,
                'title': inv.invoice_number or f'Lev.fakt #{inv.id}',
                'subtitle': inv.supplier.name if inv.supplier else '',
                'url': url_for('invoices.supplier_invoices'),
                'icon': 'bi-receipt',
            }
            for inv in si
        ]

    # Customer invoices
    ci = (
        CustomerInvoice.query
        .join(Customer, CustomerInvoice.customer_id == Customer.id)
        .filter(CustomerInvoice.company_id == company_id)
        .filter(
            db.or_(
                CustomerInvoice.invoice_number.ilike(pattern),
                Customer.name.ilike(pattern),
            )
        )
        .order_by(CustomerInvoice.invoice_date.desc())
        .limit(limit)
        .all()
    )
    if ci:
        results['customer_invoices'] = [
            {
                'id': inv.id,
                'title': inv.invoice_number or f'Kundfakt #{inv.id}',
                'subtitle': inv.customer.name if inv.customer else '',
                'url': url_for('invoices.customer_invoice_detail',
                               invoice_id=inv.id),
                'icon': 'bi-file-earmark-text',
            }
            for inv in ci
        ]

    # Accounts
    accts = (
        Account.query
        .filter(Account.company_id == company_id)
        .filter(
            db.or_(
                Account.account_number.ilike(pattern),
                Account.name.ilike(pattern),
            )
        )
        .order_by(Account.account_number)
        .limit(limit)
        .all()
    )
    if accts:
        results['accounts'] = [
            {
                'id': a.id,
                'title': a.account_number,
                'subtitle': a.name,
                'url': url_for('comparison.drilldown',
                               account_number=a.account_number),
                'icon': 'bi-list-ol',
            }
            for a in accts
        ]

    # Documents
    docs = (
        Document.query
        .filter(Document.company_id == company_id)
        .filter(
            db.or_(
                Document.file_name.ilike(pattern),
                Document.description.ilike(pattern),
            )
        )
        .order_by(Document.created_at.desc())
        .limit(limit)
        .all()
    )
    if docs:
        results['documents'] = [
            {
                'id': d.id,
                'title': d.file_name or f'Dokument #{d.id}',
                'subtitle': d.description or '',
                'url': url_for('documents.view', doc_id=d.id),
                'icon': 'bi-folder2-open',
            }
            for d in docs
        ]

    # Customers — link to list (no detail page)
    custs = (
        Customer.query
        .filter(Customer.company_id == company_id)
        .filter(
            db.or_(
                Customer.name.ilike(pattern),
                Customer.org_number.ilike(pattern),
            )
        )
        .order_by(Customer.name)
        .limit(limit)
        .all()
    )
    if custs:
        results['customers'] = [
            {
                'id': c.id,
                'title': c.name,
                'subtitle': c.org_number or '',
                'url': url_for('invoices.customers'),
                'icon': 'bi-person',
            }
            for c in custs
        ]

    # Suppliers — link to list (no detail page)
    supps = (
        Supplier.query
        .filter(Supplier.company_id == company_id)
        .filter(
            db.or_(
                Supplier.name.ilike(pattern),
                Supplier.org_number.ilike(pattern),
            )
        )
        .order_by(Supplier.name)
        .limit(limit)
        .all()
    )
    if supps:
        results['suppliers'] = [
            {
                'id': s.id,
                'title': s.name,
                'subtitle': s.org_number or '',
                'url': url_for('invoices.suppliers'),
                'icon': 'bi-truck',
            }
            for s in supps
        ]

    # Employees
    emps = (
        Employee.query
        .filter(Employee.company_id == company_id)
        .filter(
            db.or_(
                Employee.first_name.ilike(pattern),
                Employee.last_name.ilike(pattern),
                Employee.personal_number.ilike(pattern),
            )
        )
        .order_by(Employee.last_name)
        .limit(limit)
        .all()
    )
    if emps:
        results['employees'] = [
            {
                'id': e.id,
                'title': e.full_name,
                'subtitle': e.masked_personal_number or '',
                'url': url_for('salary.employee_edit', employee_id=e.id),
                'icon': 'bi-people',
            }
            for e in emps
        ]

    return results

"""Tests for Batch Operations (Phase 7C)."""

from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO

import pytest

from app.extensions import db as _db
from app.models.company import Company
from app.models.user import User
from app.models.accounting import FiscalYear, Account, Verification, VerificationRow
from app.models.invoice import Supplier, SupplierInvoice, Customer, CustomerInvoice
from app.models.document import Document
from app.models.audit import AuditLog
from app.services.batch_service import (
    batch_approve_supplier_invoices, batch_delete_verifications,
    batch_delete_documents, batch_export_verifications,
    batch_export_supplier_invoices, batch_export_customer_invoices,
    batch_export_documents,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def batch_company(db):
    """Company with verifications, invoices, and documents for batch testing."""
    co = Company(name='Batch AB', org_number='556900-0088', company_type='AB')
    db.session.add(co)
    db.session.flush()

    today = date.today()
    fy = FiscalYear(
        company_id=co.id, year=today.year,
        start_date=date(today.year, 1, 1),
        end_date=date(today.year, 12, 31),
        status='open',
    )
    db.session.add(fy)
    db.session.flush()

    acct = Account(company_id=co.id, account_number='1930', name='Företagskonto', account_type='asset')
    acct2 = Account(company_id=co.id, account_number='5010', name='Lokalhyra', account_type='expense')
    db.session.add_all([acct, acct2])
    db.session.flush()

    # Create 3 verifications
    vers = []
    for i in range(1, 4):
        v = Verification(
            company_id=co.id, fiscal_year_id=fy.id,
            verification_number=i,
            verification_date=today - timedelta(days=i),
            description=f'Betalning {i}',
        )
        db.session.add(v)
        db.session.flush()
        db.session.add(VerificationRow(
            verification_id=v.id, account_id=acct.id,
            debit=Decimal('1000'), credit=Decimal('0'),
        ))
        db.session.add(VerificationRow(
            verification_id=v.id, account_id=acct2.id,
            debit=Decimal('0'), credit=Decimal('1000'),
        ))
        vers.append(v)

    # Supplier + 3 supplier invoices
    sup = Supplier(company_id=co.id, name='Leverantör Batch', org_number='556100-8888')
    db.session.add(sup)
    db.session.flush()
    sinvs = []
    for i in range(1, 4):
        si = SupplierInvoice(
            company_id=co.id, supplier_id=sup.id,
            invoice_number=f'SI-{i}',
            invoice_date=today - timedelta(days=i),
            due_date=today + timedelta(days=30 - i),
            total_amount=Decimal('5000'),
            status='pending',
        )
        db.session.add(si)
        sinvs.append(si)

    # Customer + 3 customer invoices
    cust = Customer(company_id=co.id, name='Kund Batch', org_number='556200-7777')
    db.session.add(cust)
    db.session.flush()
    cinvs = []
    for i in range(1, 4):
        ci = CustomerInvoice(
            company_id=co.id, customer_id=cust.id,
            invoice_number=f'CI-{i}',
            invoice_date=today - timedelta(days=i),
            due_date=today + timedelta(days=30 - i),
            total_amount=Decimal('3000'),
            status='draft',
        )
        db.session.add(ci)
        cinvs.append(ci)

    # 3 documents
    docs = []
    for i in range(1, 4):
        d = Document(
            company_id=co.id, file_name=f'doc_{i}.pdf',
            document_type='faktura', description=f'Dokument {i}',
        )
        db.session.add(d)
        docs.append(d)

    db.session.commit()

    user = User.query.filter_by(username='admin').first()
    if not user:
        user = User(username='batch_admin', email='batch@test.com', role='admin')
        user.set_password('testpass123')
        db.session.add(user)
        db.session.commit()

    return {
        'company': co, 'fy': fy, 'user': user,
        'verifications': vers,
        'supplier_invoices': sinvs,
        'customer_invoices': cinvs,
        'documents': docs,
        'supplier': sup, 'customer': cust,
    }


# ---------------------------------------------------------------------------
# Service Tests — Approve
# ---------------------------------------------------------------------------

class TestBatchApprove:
    def test_approve_supplier_invoices(self, app, db, batch_company):
        with app.app_context():
            d = batch_company
            ids = [si.id for si in d['supplier_invoices']]
            result = batch_approve_supplier_invoices(ids, d['company'].id, d['user'].id)
            assert result['approved'] == 3
            assert result['errors'] == []
            for si_id in ids:
                si = db.session.get(SupplierInvoice, si_id)
                assert si.status == 'approved'

    def test_approve_already_approved(self, app, db, batch_company):
        with app.app_context():
            d = batch_company
            si_id = d['supplier_invoices'][0].id
            si = db.session.get(SupplierInvoice, si_id)
            si.status = 'approved'
            db.session.commit()
            result = batch_approve_supplier_invoices([si_id], d['company'].id, d['user'].id)
            assert result['approved'] == 0  # skipped silently

    def test_approve_wrong_company(self, app, db, batch_company):
        with app.app_context():
            d = batch_company
            ids = [d['supplier_invoices'][0].id]
            result = batch_approve_supplier_invoices(ids, d['company'].id + 999, d['user'].id)
            assert result['approved'] == 0
            assert len(result['errors']) == 1

    def test_approve_paid_status_error(self, app, db, batch_company):
        with app.app_context():
            d = batch_company
            si_id = d['supplier_invoices'][0].id
            si = db.session.get(SupplierInvoice, si_id)
            si.status = 'paid'
            db.session.commit()
            result = batch_approve_supplier_invoices([si_id], d['company'].id, d['user'].id)
            assert result['approved'] == 0
            assert len(result['errors']) == 1


# ---------------------------------------------------------------------------
# Service Tests — Delete
# ---------------------------------------------------------------------------

class TestBatchDelete:
    def test_delete_verifications(self, app, db, batch_company):
        with app.app_context():
            d = batch_company
            ids = [v.id for v in d['verifications'][:2]]
            result = batch_delete_verifications(ids, d['company'].id, d['user'].id)
            assert result['deleted'] == 2
            assert result['errors'] == []
            remaining = Verification.query.filter_by(company_id=d['company'].id).count()
            assert remaining == 1

    def test_delete_verifications_wrong_company(self, app, db, batch_company):
        with app.app_context():
            d = batch_company
            ids = [d['verifications'][0].id]
            result = batch_delete_verifications(ids, d['company'].id + 999, d['user'].id)
            assert result['deleted'] == 0
            assert len(result['errors']) == 1

    def test_delete_documents(self, app, db, batch_company):
        with app.app_context():
            d = batch_company
            ids = [doc.id for doc in d['documents']]
            result = batch_delete_documents(ids, d['company'].id, d['user'].id)
            assert result['deleted'] == 3
            assert result['errors'] == []


# ---------------------------------------------------------------------------
# Service Tests — Export
# ---------------------------------------------------------------------------

class TestBatchExport:
    def test_export_verifications(self, app, batch_company):
        with app.app_context():
            d = batch_company
            ids = [v.id for v in d['verifications']]
            output = batch_export_verifications(ids, d['company'].id)
            assert isinstance(output, BytesIO)
            content = output.getvalue().decode('utf-8-sig')
            assert 'Nummer' in content
            assert 'Betalning' in content

    def test_export_supplier_invoices(self, app, batch_company):
        with app.app_context():
            d = batch_company
            ids = [si.id for si in d['supplier_invoices']]
            output = batch_export_supplier_invoices(ids, d['company'].id)
            content = output.getvalue().decode('utf-8-sig')
            assert 'Fakturanummer' in content
            assert 'SI-1' in content

    def test_export_customer_invoices(self, app, batch_company):
        with app.app_context():
            d = batch_company
            ids = [ci.id for ci in d['customer_invoices']]
            output = batch_export_customer_invoices(ids, d['company'].id)
            content = output.getvalue().decode('utf-8-sig')
            assert 'Fakturanummer' in content
            assert 'CI-1' in content

    def test_export_documents(self, app, batch_company):
        with app.app_context():
            d = batch_company
            ids = [doc.id for doc in d['documents']]
            output = batch_export_documents(ids, d['company'].id)
            content = output.getvalue().decode('utf-8-sig')
            assert 'Filnamn' in content
            assert 'doc_1.pdf' in content

    def test_export_verifications_csv_headers(self, app, batch_company):
        with app.app_context():
            d = batch_company
            ids = [d['verifications'][0].id]
            output = batch_export_verifications(ids, d['company'].id)
            header_line = output.getvalue().decode('utf-8-sig').split('\n')[0]
            assert 'Nummer' in header_line
            assert 'Datum' in header_line
            assert 'Beskrivning' in header_line


# ---------------------------------------------------------------------------
# Service Tests — Audit Log
# ---------------------------------------------------------------------------

class TestBatchAuditLog:
    def test_delete_creates_audit_log(self, app, db, batch_company):
        with app.app_context():
            d = batch_company
            ids = [d['verifications'][0].id]
            batch_delete_verifications(ids, d['company'].id, d['user'].id)
            logs = AuditLog.query.filter_by(
                entity_type='verification', action='delete',
            ).all()
            assert len(logs) >= 1

    def test_approve_creates_audit_log(self, app, db, batch_company):
        with app.app_context():
            d = batch_company
            ids = [d['supplier_invoices'][0].id]
            batch_approve_supplier_invoices(ids, d['company'].id, d['user'].id)
            logs = AuditLog.query.filter_by(
                entity_type='supplier_invoice', action='approve',
            ).all()
            assert len(logs) >= 1


# ---------------------------------------------------------------------------
# Route Tests
# ---------------------------------------------------------------------------

class TestBatchRoutes:
    def test_approve_route(self, logged_in_client, batch_company):
        d = batch_company
        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = d['company'].id
        ids = ','.join(str(si.id) for si in d['supplier_invoices'])
        resp = logged_in_client.post('/batch/supplier-invoices/approve',
                                     data={'ids': ids},
                                     follow_redirects=True)
        assert resp.status_code == 200
        assert 'godkända' in resp.data.decode()

    def test_delete_verifications_route(self, logged_in_client, batch_company):
        d = batch_company
        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = d['company'].id
        ids = str(d['verifications'][0].id)
        resp = logged_in_client.post('/batch/verifications/delete',
                                     data={'ids': ids},
                                     follow_redirects=True)
        assert resp.status_code == 200
        assert 'borttagna' in resp.data.decode()

    def test_delete_documents_route(self, logged_in_client, batch_company):
        d = batch_company
        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = d['company'].id
        ids = str(d['documents'][0].id)
        resp = logged_in_client.post('/batch/documents/delete',
                                     data={'ids': ids},
                                     follow_redirects=True)
        assert resp.status_code == 200
        assert 'borttagna' in resp.data.decode()

    def test_export_route_csv(self, logged_in_client, batch_company):
        d = batch_company
        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = d['company'].id
        ids = ','.join(str(v.id) for v in d['verifications'])
        resp = logged_in_client.post('/batch/verifications/export',
                                     data={'ids': ids})
        assert resp.status_code == 200
        assert resp.content_type == 'text/csv; charset=utf-8'

    def test_requires_login(self, client):
        resp = client.post('/batch/verifications/delete', data={'ids': '1'})
        assert resp.status_code == 302

    def test_empty_ids(self, logged_in_client, batch_company):
        d = batch_company
        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = d['company'].id
        resp = logged_in_client.post('/batch/verifications/delete',
                                     data={'ids': ''},
                                     follow_redirects=True)
        assert resp.status_code == 200
        assert 'Inga verifikationer markerade' in resp.data.decode()

    def test_no_company(self, logged_in_client):
        resp = logged_in_client.post('/batch/verifications/delete',
                                     data={'ids': '1'},
                                     follow_redirects=True)
        assert resp.status_code == 200

    def test_readonly_cannot_delete(self, app, db, readonly_user, batch_company):
        d = batch_company
        client = app.test_client()
        client.post('/login', data={
            'username': 'reader',
            'password': 'testpass123',
        }, follow_redirects=True)
        with client.session_transaction() as sess:
            sess['active_company_id'] = d['company'].id
        ids = str(d['verifications'][0].id)
        resp = client.post('/batch/verifications/delete',
                           data={'ids': ids},
                           follow_redirects=True)
        assert resp.status_code == 200
        assert 'Skrivskyddad' in resp.data.decode()

    def test_mixed_valid_invalid_ids(self, app, db, batch_company):
        with app.app_context():
            d = batch_company
            ids = [d['verifications'][0].id, 99999]
            result = batch_delete_verifications(ids, d['company'].id, d['user'].id)
            assert result['deleted'] == 1
            assert len(result['errors']) == 1


# ---------------------------------------------------------------------------
# Template Tests
# ---------------------------------------------------------------------------

class TestBatchTemplates:
    def test_accounting_has_batch_checkbox(self, logged_in_client, batch_company):
        d = batch_company
        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = d['company'].id
        resp = logged_in_client.get('/accounting/')
        html = resp.data.decode()
        assert 'batch-select-all' in html
        assert 'batch-checkbox' in html
        assert 'batch-toolbar' in html

    def test_supplier_invoices_has_batch(self, logged_in_client, batch_company):
        d = batch_company
        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = d['company'].id
        resp = logged_in_client.get('/invoices/supplier-invoices')
        html = resp.data.decode()
        assert 'batch-select-all' in html
        assert 'batch-toolbar' in html

    def test_customer_invoices_has_batch(self, logged_in_client, batch_company):
        d = batch_company
        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = d['company'].id
        resp = logged_in_client.get('/invoices/customer-invoices')
        html = resp.data.decode()
        assert 'batch-select-all' in html
        assert 'batch-toolbar' in html

    def test_documents_has_batch(self, logged_in_client, batch_company):
        d = batch_company
        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = d['company'].id
        resp = logged_in_client.get('/documents/')
        html = resp.data.decode()
        assert 'batch-select-all' in html
        assert 'batch-toolbar' in html

"""Tests for document management service (Phase 4D)."""
import os
import io
from datetime import date
from decimal import Decimal

import pytest

from app.models.company import Company
from app.models.accounting import FiscalYear, Account, Verification, VerificationRow
from app.models.invoice import Supplier, SupplierInvoice
from app.models.user import User
from app.models.document import Document
from app.services.document_service import (
    upload_document, get_documents, attach_to_verification,
    attach_to_invoice, detach_document, delete_document,
    get_document_file_path,
)


class FakeFile:
    """Mimic werkzeug FileStorage for testing uploads."""
    def __init__(self, filename, content=b'fake file content'):
        self.filename = filename
        self._content = content

    def save(self, path):
        with open(path, 'wb') as f:
            f.write(self._content)


@pytest.fixture
def doc_company(db, app):
    """Company, FY, verification, supplier invoice, and upload dir."""
    co = Company(name='Doc AB', org_number='556600-0030', company_type='AB')
    db.session.add(co)
    db.session.flush()

    fy = FiscalYear(company_id=co.id, year=2025, start_date=date(2025, 1, 1),
                    end_date=date(2025, 12, 31), status='open')
    db.session.add(fy)
    db.session.flush()

    cash = Account(company_id=co.id, account_number='1930',
                   name='Företagskonto', account_type='asset')
    expense = Account(company_id=co.id, account_number='5010',
                      name='Lokalhyra', account_type='expense')
    db.session.add_all([cash, expense])
    db.session.flush()

    v = Verification(company_id=co.id, fiscal_year_id=fy.id,
                     verification_number=1, verification_date=date(2025, 1, 15))
    db.session.add(v)
    db.session.flush()
    db.session.add_all([
        VerificationRow(verification_id=v.id, account_id=cash.id,
                        debit=Decimal('1000'), credit=Decimal('0')),
        VerificationRow(verification_id=v.id, account_id=expense.id,
                        debit=Decimal('0'), credit=Decimal('1000')),
    ])

    supplier = Supplier(company_id=co.id, name='Lev AB', org_number='556800-0001')
    db.session.add(supplier)
    db.session.flush()

    si = SupplierInvoice(company_id=co.id, supplier_id=supplier.id,
                         invoice_number='LF-001', invoice_date=date(2025, 1, 10),
                         due_date=date(2025, 2, 10), total_amount=Decimal('5000'))
    db.session.add(si)

    user = User(username='docuser', email='doc@test.com', role='admin')
    user.set_password('test123')
    db.session.add(user)
    db.session.commit()

    # Ensure upload directory exists
    upload_dir = os.path.join(app.static_folder, 'uploads', str(co.id))
    os.makedirs(upload_dir, exist_ok=True)

    return {'company': co, 'fy': fy, 'verification': v,
            'supplier_invoice': si, 'user': user}


class TestUpload:
    def test_upload_document(self, doc_company, app):
        co = doc_company['company']
        user = doc_company['user']
        fake_file = FakeFile('test_receipt.pdf')

        with app.app_context():
            doc, err = upload_document(co.id, fake_file, 'kvitto',
                                       description='Test kvitto', user_id=user.id)
            assert err is None
            assert doc is not None
            assert doc.file_name == 'test_receipt.pdf'
            assert doc.mime_type == 'application/pdf'

    def test_upload_no_file(self, doc_company, app):
        co = doc_company['company']
        with app.app_context():
            doc, err = upload_document(co.id, None, 'kvitto')
        assert doc is None
        assert err is not None


class TestList:
    def test_get_documents(self, doc_company, app):
        co = doc_company['company']
        user = doc_company['user']
        with app.app_context():
            upload_document(co.id, FakeFile('doc1.pdf'), 'kvitto', user_id=user.id)
            upload_document(co.id, FakeFile('doc2.png'), 'avtal', user_id=user.id)
            result = get_documents(co.id)
        assert result.total == 2

    def test_filter_by_type(self, doc_company, app):
        co = doc_company['company']
        user = doc_company['user']
        with app.app_context():
            upload_document(co.id, FakeFile('doc1.pdf'), 'kvitto', user_id=user.id)
            upload_document(co.id, FakeFile('doc2.png'), 'avtal', user_id=user.id)
            result = get_documents(co.id, doc_type='kvitto')
        assert result.total == 1


class TestAttach:
    def test_attach_to_verification(self, doc_company, app):
        co = doc_company['company']
        user = doc_company['user']
        with app.app_context():
            doc, _ = upload_document(co.id, FakeFile('attach.pdf'), 'kvitto', user_id=user.id)
            result = attach_to_verification(doc.id, doc_company['verification'].id, user.id)
        assert result is True

    def test_attach_to_invoice(self, doc_company, app):
        co = doc_company['company']
        user = doc_company['user']
        with app.app_context():
            doc, _ = upload_document(co.id, FakeFile('inv.pdf'), 'faktura', user_id=user.id)
            result = attach_to_invoice(doc.id, doc_company['supplier_invoice'].id,
                                       'supplier', user.id)
        assert result is True

    def test_detach(self, doc_company, app):
        co = doc_company['company']
        user = doc_company['user']
        with app.app_context():
            doc, _ = upload_document(co.id, FakeFile('detach.pdf'), 'kvitto', user_id=user.id)
            attach_to_verification(doc.id, doc_company['verification'].id, user.id)
            result = detach_document(doc.id, user.id)
        assert result is True


class TestDelete:
    def test_delete_document(self, doc_company, app):
        co = doc_company['company']
        user = doc_company['user']
        with app.app_context():
            doc, _ = upload_document(co.id, FakeFile('delete_me.pdf'), 'kvitto', user_id=user.id)
            doc_id = doc.id
            result = delete_document(doc_id, user.id)
        assert result is True
        from app.extensions import db
        assert db.session.get(Document, doc_id) is None


class TestPath:
    def test_get_file_path(self, doc_company, app):
        co = doc_company['company']
        user = doc_company['user']
        with app.app_context():
            doc, _ = upload_document(co.id, FakeFile('path_test.pdf'), 'kvitto', user_id=user.id)
            path, mime = get_document_file_path(doc.id)
        assert path is not None
        assert mime == 'application/pdf'

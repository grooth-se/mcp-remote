"""Security tests: cross-company access, readonly permissions, path traversal, CSRF meta."""

import os
from datetime import date
from decimal import Decimal

import pytest

from app.extensions import db as _db
from app.models.company import Company
from app.models.accounting import FiscalYear, Account, Verification, VerificationRow
from app.models.invoice import Supplier, SupplierInvoice, Customer, CustomerInvoice
from app.models.document import Document
from app.models.tax import VATReport, Deadline
from app.models.bank import BankAccount, BankTransaction
from app.utils.security import safe_path


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def two_companies(db, logged_in_client):
    """Create company A (active) and company B (other), each with FY + data."""
    # --- Company A ---
    co_a = Company(name='Företag A', org_number='556600-0001', company_type='AB')
    db.session.add(co_a)
    db.session.flush()

    fy_a = FiscalYear(company_id=co_a.id, year=2025,
                      start_date=date(2025, 1, 1), end_date=date(2025, 12, 31),
                      status='open')
    db.session.add(fy_a)
    db.session.flush()

    acct_a = Account(company_id=co_a.id, account_number='1930',
                     name='Kassa A', account_type='asset')
    acct_a2 = Account(company_id=co_a.id, account_number='4000',
                      name='Inköp A', account_type='expense')
    db.session.add_all([acct_a, acct_a2])
    db.session.flush()

    ver_a = Verification(company_id=co_a.id, fiscal_year_id=fy_a.id,
                         verification_number=1, verification_date=date(2025, 6, 1),
                         description='Test A')
    db.session.add(ver_a)
    db.session.flush()
    db.session.add_all([
        VerificationRow(verification_id=ver_a.id, account_id=acct_a.id,
                        debit=Decimal('100'), credit=Decimal('0')),
        VerificationRow(verification_id=ver_a.id, account_id=acct_a2.id,
                        debit=Decimal('0'), credit=Decimal('100')),
    ])

    sup_a = Supplier(company_id=co_a.id, name='Leverantör A')
    db.session.add(sup_a)
    db.session.flush()

    sinv_a = SupplierInvoice(company_id=co_a.id, supplier_id=sup_a.id,
                             invoice_number='FA-001', invoice_date=date(2025, 6, 1),
                             due_date=date(2025, 7, 1), total_amount=Decimal('1000'),
                             status='pending')
    db.session.add(sinv_a)
    db.session.flush()

    cust_a = Customer(company_id=co_a.id, name='Kund A')
    db.session.add(cust_a)
    db.session.flush()

    cinv_a = CustomerInvoice(company_id=co_a.id, customer_id=cust_a.id,
                             invoice_number='KF-001', invoice_date=date(2025, 6, 1),
                             due_date=date(2025, 7, 1), total_amount=Decimal('2000'),
                             status='draft')
    db.session.add(cinv_a)
    db.session.flush()

    doc_a = Document(company_id=co_a.id, document_type='faktura',
                     file_name='test_a.pdf', file_path='uploads/1/test_a.pdf',
                     mime_type='application/pdf')
    db.session.add(doc_a)
    db.session.flush()

    # --- Company B ---
    co_b = Company(name='Företag B', org_number='556600-0002', company_type='AB')
    db.session.add(co_b)
    db.session.flush()

    fy_b = FiscalYear(company_id=co_b.id, year=2025,
                      start_date=date(2025, 1, 1), end_date=date(2025, 12, 31),
                      status='open')
    db.session.add(fy_b)
    db.session.flush()

    acct_b = Account(company_id=co_b.id, account_number='1930',
                     name='Kassa B', account_type='asset')
    acct_b2 = Account(company_id=co_b.id, account_number='4000',
                      name='Inköp B', account_type='expense')
    db.session.add_all([acct_b, acct_b2])
    db.session.flush()

    ver_b = Verification(company_id=co_b.id, fiscal_year_id=fy_b.id,
                         verification_number=1, verification_date=date(2025, 6, 1),
                         description='Test B')
    db.session.add(ver_b)
    db.session.flush()
    db.session.add_all([
        VerificationRow(verification_id=ver_b.id, account_id=acct_b.id,
                        debit=Decimal('200'), credit=Decimal('0')),
        VerificationRow(verification_id=ver_b.id, account_id=acct_b2.id,
                        debit=Decimal('0'), credit=Decimal('200')),
    ])

    sup_b = Supplier(company_id=co_b.id, name='Leverantör B')
    db.session.add(sup_b)
    db.session.flush()

    sinv_b = SupplierInvoice(company_id=co_b.id, supplier_id=sup_b.id,
                             invoice_number='FB-001', invoice_date=date(2025, 6, 1),
                             due_date=date(2025, 7, 1), total_amount=Decimal('3000'),
                             status='pending')
    db.session.add(sinv_b)
    db.session.flush()

    cust_b = Customer(company_id=co_b.id, name='Kund B')
    db.session.add(cust_b)
    db.session.flush()

    cinv_b = CustomerInvoice(company_id=co_b.id, customer_id=cust_b.id,
                             invoice_number='KB-001', invoice_date=date(2025, 6, 1),
                             due_date=date(2025, 7, 1), total_amount=Decimal('4000'),
                             status='draft')
    db.session.add(cinv_b)
    db.session.flush()

    doc_b = Document(company_id=co_b.id, document_type='faktura',
                     file_name='test_b.pdf', file_path='uploads/2/test_b.pdf',
                     mime_type='application/pdf')
    db.session.add(doc_b)
    db.session.flush()

    vat_b = VATReport(company_id=co_b.id, fiscal_year_id=fy_b.id,
                      period_type='quarterly', period_year=2025, period_quarter=1,
                      period_start=date(2025, 1, 1), period_end=date(2025, 3, 31),
                      output_vat_25=Decimal('250'), output_vat_12=Decimal('0'),
                      output_vat_6=Decimal('0'), input_vat=Decimal('100'),
                      vat_to_pay=Decimal('150'), status='draft')
    db.session.add(vat_b)
    db.session.flush()

    deadline_b = Deadline(company_id=co_b.id, deadline_type='moms',
                          description='Moms Q1', due_date=date(2025, 5, 12),
                          status='pending')
    db.session.add(deadline_b)
    db.session.flush()

    txn_b = BankTransaction(
        company_id=co_b.id, bank_account_id=0,
        transaction_date=date(2025, 3, 15), description='Test',
        amount=Decimal('-500'), status='unmatched',
    )
    # We need a bank account for company B for the transaction
    ba_b = BankAccount(company_id=co_b.id, bank_name='SEB', account_number='99990001')
    db.session.add(ba_b)
    db.session.flush()
    txn_b.bank_account_id = ba_b.id
    db.session.add(txn_b)

    db.session.commit()

    # Set session to Company A
    with logged_in_client.session_transaction() as sess:
        sess['active_company_id'] = co_a.id

    return {
        'co_a': co_a, 'fy_a': fy_a, 'ver_a': ver_a,
        'sinv_a': sinv_a, 'cinv_a': cinv_a, 'doc_a': doc_a,
        'co_b': co_b, 'fy_b': fy_b, 'ver_b': ver_b,
        'sinv_b': sinv_b, 'cinv_b': cinv_b, 'doc_b': doc_b,
        'vat_b': vat_b, 'deadline_b': deadline_b, 'txn_b': txn_b,
    }


# ---------------------------------------------------------------------------
# Cross-company access tests
# ---------------------------------------------------------------------------

class TestCrossCompanyAccess:
    """Verify that company A session cannot access company B's entities."""

    def test_view_other_company_verification(self, two_companies, logged_in_client):
        ver_b = two_companies['ver_b']
        resp = logged_in_client.get(f'/accounting/verification/{ver_b.id}',
                                    follow_redirects=True)
        assert 'hittades inte' in resp.data.decode()

    def test_approve_other_company_supplier_invoice(self, two_companies, logged_in_client):
        sinv_b = two_companies['sinv_b']
        resp = logged_in_client.post(
            f'/invoices/supplier-invoices/{sinv_b.id}/approve',
            follow_redirects=True)
        assert 'hittades inte' in resp.data.decode()
        # Verify status unchanged
        _db.session.refresh(sinv_b)
        assert sinv_b.status == 'pending'

    def test_pay_other_company_supplier_invoice(self, two_companies, logged_in_client):
        sinv_b = two_companies['sinv_b']
        resp = logged_in_client.post(
            f'/invoices/supplier-invoices/{sinv_b.id}/pay',
            follow_redirects=True)
        assert 'hittades inte' in resp.data.decode()
        _db.session.refresh(sinv_b)
        assert sinv_b.status == 'pending'

    def test_send_other_company_customer_invoice(self, two_companies, logged_in_client):
        cinv_b = two_companies['cinv_b']
        resp = logged_in_client.post(
            f'/invoices/customer-invoices/{cinv_b.id}/send',
            follow_redirects=True)
        assert 'hittades inte' in resp.data.decode()
        _db.session.refresh(cinv_b)
        assert cinv_b.status == 'draft'

    def test_mark_paid_other_company_customer_invoice(self, two_companies, logged_in_client):
        cinv_b = two_companies['cinv_b']
        resp = logged_in_client.post(
            f'/invoices/customer-invoices/{cinv_b.id}/mark-paid',
            follow_redirects=True)
        assert 'hittades inte' in resp.data.decode()
        _db.session.refresh(cinv_b)
        assert cinv_b.status == 'draft'

    def test_download_other_company_document(self, two_companies, logged_in_client):
        doc_b = two_companies['doc_b']
        resp = logged_in_client.get(f'/documents/{doc_b.id}/download',
                                    follow_redirects=True)
        assert 'hittades inte' in resp.data.decode()

    def test_preview_other_company_document(self, two_companies, logged_in_client):
        doc_b = two_companies['doc_b']
        resp = logged_in_client.get(f'/documents/{doc_b.id}/preview',
                                    follow_redirects=True)
        assert 'hittades inte' in resp.data.decode()

    def test_delete_other_company_document(self, two_companies, logged_in_client):
        doc_b = two_companies['doc_b']
        resp = logged_in_client.post(f'/documents/{doc_b.id}/delete',
                                     follow_redirects=True)
        assert 'hittades inte' in resp.data.decode()
        # Document still exists
        assert _db.session.get(Document, doc_b.id) is not None

    def test_view_other_company_vat_report(self, two_companies, logged_in_client):
        vat_b = two_companies['vat_b']
        resp = logged_in_client.get(f'/tax/vat/{vat_b.id}',
                                    follow_redirects=True)
        assert 'hittades inte' in resp.data.decode()

    def test_finalize_other_company_vat_report(self, two_companies, logged_in_client):
        vat_b = two_companies['vat_b']
        resp = logged_in_client.post(f'/tax/vat/{vat_b.id}/finalize',
                                     follow_redirects=True)
        assert 'hittades inte' in resp.data.decode()
        _db.session.refresh(vat_b)
        assert vat_b.status == 'draft'

    def test_complete_other_company_deadline(self, two_companies, logged_in_client):
        deadline_b = two_companies['deadline_b']
        resp = logged_in_client.post(
            f'/tax/deadlines/{deadline_b.id}/complete',
            data={'notes': ''},
            follow_redirects=True)
        assert 'hittades inte' in resp.data.decode()
        _db.session.refresh(deadline_b)
        assert deadline_b.status == 'pending'

    def test_unmatch_other_company_transaction(self, two_companies, logged_in_client):
        txn_b = two_companies['txn_b']
        resp = logged_in_client.post(
            f'/bank/transactions/{txn_b.id}/unmatch',
            follow_redirects=True)
        assert 'hittades inte' in resp.data.decode()

    def test_ignore_other_company_transaction(self, two_companies, logged_in_client):
        txn_b = two_companies['txn_b']
        resp = logged_in_client.post(
            f'/bank/transactions/{txn_b.id}/ignore',
            follow_redirects=True)
        assert 'hittades inte' in resp.data.decode()

    def test_close_other_company_fy(self, two_companies, logged_in_client):
        fy_b = two_companies['fy_b']
        resp = logged_in_client.post(f'/closing/{fy_b.id}/close',
                                     follow_redirects=True)
        assert 'hittades inte' in resp.data.decode()
        _db.session.refresh(fy_b)
        assert fy_b.status == 'open'

    def test_preview_close_other_company_fy(self, two_companies, logged_in_client):
        fy_b = two_companies['fy_b']
        resp = logged_in_client.get(f'/closing/{fy_b.id}/preview',
                                    follow_redirects=True)
        assert 'hittades inte' in resp.data.decode()


# ---------------------------------------------------------------------------
# Readonly permission tests
# ---------------------------------------------------------------------------

@pytest.fixture
def readonly_setup(db, readonly_client):
    """Create company and data for readonly tests."""
    co = Company(name='Readonly AB', org_number='556600-9001', company_type='AB')
    db.session.add(co)
    db.session.flush()

    fy = FiscalYear(company_id=co.id, year=2025,
                    start_date=date(2025, 1, 1), end_date=date(2025, 12, 31),
                    status='open')
    db.session.add(fy)
    db.session.flush()

    acct1 = Account(company_id=co.id, account_number='1930',
                    name='Kassa', account_type='asset')
    acct2 = Account(company_id=co.id, account_number='4000',
                    name='Inköp', account_type='expense')
    db.session.add_all([acct1, acct2])
    db.session.flush()

    ver = Verification(company_id=co.id, fiscal_year_id=fy.id,
                       verification_number=1, verification_date=date(2025, 6, 1))
    db.session.add(ver)
    db.session.flush()
    db.session.add_all([
        VerificationRow(verification_id=ver.id, account_id=acct1.id,
                        debit=Decimal('100'), credit=Decimal('0')),
        VerificationRow(verification_id=ver.id, account_id=acct2.id,
                        debit=Decimal('0'), credit=Decimal('100')),
    ])

    sup = Supplier(company_id=co.id, name='Leverantör RO')
    db.session.add(sup)
    db.session.flush()

    sinv = SupplierInvoice(company_id=co.id, supplier_id=sup.id,
                           invoice_number='RO-001', invoice_date=date(2025, 6, 1),
                           due_date=date(2025, 7, 1), total_amount=Decimal('1000'),
                           status='pending')
    db.session.add(sinv)
    db.session.flush()

    cust = Customer(company_id=co.id, name='Kund RO')
    db.session.add(cust)
    db.session.flush()

    cinv = CustomerInvoice(company_id=co.id, customer_id=cust.id,
                           invoice_number='RKF-001', invoice_date=date(2025, 6, 1),
                           due_date=date(2025, 7, 1), total_amount=Decimal('2000'),
                           status='draft')
    db.session.add(cinv)
    db.session.flush()

    doc = Document(company_id=co.id, document_type='faktura',
                   file_name='ro_test.pdf', file_path='uploads/ro/test.pdf',
                   mime_type='application/pdf')
    db.session.add(doc)
    db.session.flush()

    ba = BankAccount(company_id=co.id, bank_name='SEB', account_number='77770001')
    db.session.add(ba)
    db.session.flush()

    txn = BankTransaction(company_id=co.id, bank_account_id=ba.id,
                          transaction_date=date(2025, 3, 15), description='Test',
                          amount=Decimal('-500'), status='unmatched')
    db.session.add(txn)
    db.session.commit()

    with readonly_client.session_transaction() as sess:
        sess['active_company_id'] = co.id

    return {
        'co': co, 'fy': fy, 'ver': ver, 'sinv': sinv, 'cinv': cinv,
        'doc': doc, 'txn': txn, 'client': readonly_client,
    }


class TestReadonlyPermissions:
    """Verify that readonly users cannot perform write operations."""

    def test_readonly_cannot_approve_supplier_invoice(self, readonly_setup):
        c = readonly_setup['client']
        sinv = readonly_setup['sinv']
        resp = c.post(f'/invoices/supplier-invoices/{sinv.id}/approve',
                      follow_redirects=True)
        assert 'behörighet' in resp.data.decode()
        _db.session.refresh(sinv)
        assert sinv.status == 'pending'

    def test_readonly_cannot_pay_supplier_invoice(self, readonly_setup):
        c = readonly_setup['client']
        sinv = readonly_setup['sinv']
        resp = c.post(f'/invoices/supplier-invoices/{sinv.id}/pay',
                      follow_redirects=True)
        assert 'behörighet' in resp.data.decode()
        _db.session.refresh(sinv)
        assert sinv.status == 'pending'

    def test_readonly_cannot_send_customer_invoice(self, readonly_setup):
        c = readonly_setup['client']
        cinv = readonly_setup['cinv']
        resp = c.post(f'/invoices/customer-invoices/{cinv.id}/send',
                      follow_redirects=True)
        assert 'behörighet' in resp.data.decode()
        _db.session.refresh(cinv)
        assert cinv.status == 'draft'

    def test_readonly_cannot_mark_customer_invoice_paid(self, readonly_setup):
        c = readonly_setup['client']
        cinv = readonly_setup['cinv']
        resp = c.post(f'/invoices/customer-invoices/{cinv.id}/mark-paid',
                      follow_redirects=True)
        assert 'behörighet' in resp.data.decode()
        _db.session.refresh(cinv)
        assert cinv.status == 'draft'

    def test_readonly_cannot_delete_document(self, readonly_setup):
        c = readonly_setup['client']
        doc = readonly_setup['doc']
        resp = c.post(f'/documents/{doc.id}/delete',
                      follow_redirects=True)
        assert 'behörighet' in resp.data.decode()
        assert _db.session.get(Document, doc.id) is not None

    def test_readonly_cannot_attach_verification(self, readonly_setup):
        c = readonly_setup['client']
        doc = readonly_setup['doc']
        ver = readonly_setup['ver']
        resp = c.post(f'/documents/{doc.id}/attach-verification',
                      data={'verification_id': ver.id},
                      follow_redirects=True)
        assert 'behörighet' in resp.data.decode()

    def test_readonly_cannot_unmatch_bank_transaction(self, readonly_setup, db):
        c = readonly_setup['client']
        co = readonly_setup['co']
        ba = BankAccount.query.filter_by(company_id=co.id).first()
        txn = BankTransaction(
            company_id=co.id, bank_account_id=ba.id,
            transaction_date=date(2025, 3, 20), description='Unmatch test',
            amount=Decimal('-500'), status='matched',
        )
        db.session.add(txn)
        db.session.commit()

        resp = c.post(f'/bank/transactions/{txn.id}/unmatch',
                      follow_redirects=True)
        assert 'behörighet' in resp.data.decode()

    def test_readonly_cannot_ignore_bank_transaction(self, readonly_setup):
        c = readonly_setup['client']
        txn = readonly_setup['txn']
        resp = c.post(f'/bank/transactions/{txn.id}/ignore',
                      follow_redirects=True)
        assert 'behörighet' in resp.data.decode()


# ---------------------------------------------------------------------------
# Path traversal tests
# ---------------------------------------------------------------------------

class TestPathTraversal:
    """Test safe_path() utility and its integration."""

    def test_safe_path_normal(self, tmp_path):
        base = str(tmp_path)
        subfile = os.path.join(base, 'uploads', 'file.pdf')
        os.makedirs(os.path.join(base, 'uploads'), exist_ok=True)
        result = safe_path(base, 'uploads/file.pdf')
        assert result == os.path.realpath(subfile)

    def test_safe_path_rejects_traversal(self, tmp_path):
        base = str(tmp_path)
        with pytest.raises(ValueError, match='Path traversal'):
            safe_path(base, '../../../etc/passwd')

    def test_safe_path_rejects_absolute_escape(self, tmp_path):
        base = str(tmp_path)
        with pytest.raises(ValueError, match='Path traversal'):
            safe_path(base, '/etc/passwd')


# ---------------------------------------------------------------------------
# CSRF meta tag test
# ---------------------------------------------------------------------------

class TestCSRFMeta:
    def test_csrf_meta_present(self, logged_in_client):
        resp = logged_in_client.get('/')
        html = resp.data.decode()
        assert 'name="csrf-token"' in html

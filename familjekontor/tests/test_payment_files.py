"""Tests for Phase 9: Payment File Generation."""

import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app import create_app
from app.extensions import db as _db
from app.models.accounting import Account, FiscalYear, Verification
from app.models.bank import BankAccount
from app.models.company import Company
from app.models.invoice import Supplier, SupplierInvoice
from app.models.payment_file import PaymentFile, PaymentInstruction
from app.models.user import User
from app.services.payment_file_service import (
    cancel_batch,
    confirm_batch_paid,
    create_payment_batch,
    create_supplier_payment_verification,
    determine_payment_method,
    generate_bankgirot_file,
    generate_pain001_xml,
    generate_payment_file,
    get_next_batch_reference,
    get_payable_invoices,
    mark_batch_uploaded,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope='session')
def app():
    app = create_app('testing')
    with app.app_context():
        _db.create_all()
        yield app
        _db.drop_all()


@pytest.fixture(scope='function')
def db(app):
    with app.app_context():
        _db.create_all()
        yield _db
        _db.session.rollback()
        for table in reversed(_db.metadata.sorted_tables):
            _db.session.execute(table.delete())
        _db.session.commit()


@pytest.fixture
def admin_user(db):
    user = User(username='admin', email='admin@test.com', role='admin')
    user.set_password('testpass123')
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def logged_in_client(client, admin_user):
    client.post('/login', data={
        'username': 'admin', 'password': 'testpass123',
    }, follow_redirects=True)
    return client


@pytest.fixture
def payment_setup(db, admin_user):
    """Full setup: company, bank account, suppliers, approved invoices, FY, accounts."""
    co = Company(name='PayAB', org_number='5566112233', company_type='AB')
    db.session.add(co)
    db.session.flush()

    fy = FiscalYear(company_id=co.id, year=2026,
                    start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    db.session.add(fy)
    db.session.flush()

    # Accounts
    for num, name, atype in [
        ('1930', 'Företagskonto', 'asset'),
        ('2440', 'Leverantörsskulder', 'liability'),
    ]:
        db.session.add(Account(company_id=co.id, account_number=num, name=name, account_type=atype))
    db.session.flush()

    # Bank account
    ba = BankAccount(
        company_id=co.id, bank_name='SEB', account_number='12345678901',
        clearing_number='5000', iban='SE1234567890123456789012', bic='ESSESESS',
        ledger_account='1930',
    )
    db.session.add(ba)
    db.session.flush()

    # Supplier with bankgiro
    s1 = Supplier(company_id=co.id, name='Leverantör BG', bankgiro='123-4567')
    db.session.add(s1)
    db.session.flush()

    # Supplier with IBAN
    s2 = Supplier(company_id=co.id, name='Leverantör IBAN',
                  iban='DE89370400440532013000', bic='COBADEFFXXX')
    db.session.add(s2)
    db.session.flush()

    # Supplier with plusgiro
    s3 = Supplier(company_id=co.id, name='Leverantör PG', plusgiro='12345-6')
    db.session.add(s3)
    db.session.flush()

    # Supplier with no payment details
    s4 = Supplier(company_id=co.id, name='Leverantör Ingen')
    db.session.add(s4)
    db.session.flush()

    # Approved invoices
    inv1 = SupplierInvoice(
        company_id=co.id, supplier_id=s1.id, invoice_number='INV-001',
        invoice_date=date(2026, 2, 1), due_date=date(2026, 3, 1),
        amount_excl_vat=8000, vat_amount=2000, total_amount=10000, status='approved',
    )
    inv2 = SupplierInvoice(
        company_id=co.id, supplier_id=s2.id, invoice_number='INV-002',
        invoice_date=date(2026, 2, 5), due_date=date(2026, 3, 5),
        amount_excl_vat=4000, vat_amount=1000, total_amount=5000, status='approved',
    )
    inv3 = SupplierInvoice(
        company_id=co.id, supplier_id=s3.id, invoice_number='INV-003',
        invoice_date=date(2026, 2, 10), due_date=date(2026, 3, 10),
        amount_excl_vat=2400, vat_amount=600, total_amount=3000, status='approved',
    )
    # Pending invoice (should not be payable)
    inv4 = SupplierInvoice(
        company_id=co.id, supplier_id=s1.id, invoice_number='INV-004',
        invoice_date=date(2026, 2, 15), due_date=date(2026, 3, 15),
        amount_excl_vat=1000, vat_amount=250, total_amount=1250, status='pending',
    )
    # Invoice with no payment details
    inv5 = SupplierInvoice(
        company_id=co.id, supplier_id=s4.id, invoice_number='INV-005',
        invoice_date=date(2026, 2, 15), due_date=date(2026, 3, 15),
        amount_excl_vat=2000, vat_amount=500, total_amount=2500, status='approved',
    )
    db.session.add_all([inv1, inv2, inv3, inv4, inv5])
    db.session.commit()

    return {
        'company': co, 'fy': fy, 'bank_account': ba,
        'supplier_bg': s1, 'supplier_iban': s2, 'supplier_pg': s3, 'supplier_none': s4,
        'inv_bg': inv1, 'inv_iban': inv2, 'inv_pg': inv3,
        'inv_pending': inv4, 'inv_no_details': inv5,
        'user': admin_user,
    }


# ---------------------------------------------------------------------------
# TestPaymentMethod
# ---------------------------------------------------------------------------

class TestPaymentMethod:
    def test_determine_method_bankgiro(self, payment_setup):
        s = payment_setup['supplier_bg']
        method, account, bic = determine_payment_method(s)
        assert method == 'bankgiro'
        assert account == '123-4567'
        assert bic is None

    def test_determine_method_plusgiro(self, payment_setup):
        s = payment_setup['supplier_pg']
        method, account, bic = determine_payment_method(s)
        assert method == 'plusgiro'
        assert account == '12345-6'

    def test_determine_method_iban(self, payment_setup):
        s = payment_setup['supplier_iban']
        method, account, bic = determine_payment_method(s)
        assert method == 'iban'
        assert account == 'DE89370400440532013000'
        assert bic == 'COBADEFFXXX'

    def test_determine_method_none(self, payment_setup):
        s = payment_setup['supplier_none']
        method, account, bic = determine_payment_method(s)
        assert method is None
        assert account is None


# ---------------------------------------------------------------------------
# TestPayableInvoices
# ---------------------------------------------------------------------------

class TestPayableInvoices:
    def test_get_payable_returns_approved_only(self, payment_setup):
        co = payment_setup['company']
        invoices = get_payable_invoices(co.id)
        # inv_bg, inv_iban, inv_pg, inv_no_details are approved; inv_pending is not
        assert len(invoices) == 4
        nums = {inv.invoice_number for inv in invoices}
        assert 'INV-004' not in nums  # pending

    def test_excludes_invoices_in_active_batch(self, payment_setup):
        co = payment_setup['company']
        ba = payment_setup['bank_account']
        inv = payment_setup['inv_bg']

        pf, _ = create_payment_batch(
            co.id, ba.id, [inv.id], date(2026, 3, 1), 'pain001', payment_setup['user'].id
        )
        assert pf is not None

        invoices = get_payable_invoices(co.id)
        ids = {i.id for i in invoices}
        assert inv.id not in ids

    def test_includes_invoice_from_cancelled_batch(self, payment_setup):
        co = payment_setup['company']
        ba = payment_setup['bank_account']
        inv = payment_setup['inv_bg']

        pf, _ = create_payment_batch(
            co.id, ba.id, [inv.id], date(2026, 3, 1), 'pain001', payment_setup['user'].id
        )
        cancel_batch(pf.id, payment_setup['user'].id)

        invoices = get_payable_invoices(co.id)
        ids = {i.id for i in invoices}
        assert inv.id in ids


# ---------------------------------------------------------------------------
# TestCreateBatch
# ---------------------------------------------------------------------------

class TestCreateBatch:
    def test_create_batch_success(self, payment_setup):
        co = payment_setup['company']
        ba = payment_setup['bank_account']
        inv1 = payment_setup['inv_bg']
        inv2 = payment_setup['inv_iban']

        pf, errors = create_payment_batch(
            co.id, ba.id, [inv1.id, inv2.id], date(2026, 3, 1), 'pain001', payment_setup['user'].id
        )
        assert not errors
        assert pf is not None
        assert pf.number_of_transactions == 2
        assert pf.total_amount == Decimal('15000')
        assert pf.status == 'draft'
        assert len(pf.instructions) == 2

    def test_create_batch_rejects_non_approved(self, payment_setup):
        co = payment_setup['company']
        ba = payment_setup['bank_account']
        inv = payment_setup['inv_pending']

        pf, errors = create_payment_batch(
            co.id, ba.id, [inv.id], date(2026, 3, 1), 'pain001', payment_setup['user'].id
        )
        assert pf is None
        assert any('inte godkänd' in e for e in errors)

    def test_create_batch_rejects_missing_payment_details(self, payment_setup):
        co = payment_setup['company']
        ba = payment_setup['bank_account']
        inv = payment_setup['inv_no_details']

        pf, errors = create_payment_batch(
            co.id, ba.id, [inv.id], date(2026, 3, 1), 'pain001', payment_setup['user'].id
        )
        assert pf is None
        assert any('betalningsuppgifter' in e for e in errors)

    def test_batch_reference_sequential(self, payment_setup):
        co = payment_setup['company']
        ba = payment_setup['bank_account']
        inv1 = payment_setup['inv_bg']
        inv2 = payment_setup['inv_iban']

        pf1, _ = create_payment_batch(
            co.id, ba.id, [inv1.id], date(2026, 3, 1), 'pain001', payment_setup['user'].id
        )
        pf2, _ = create_payment_batch(
            co.id, ba.id, [inv2.id], date(2026, 3, 5), 'pain001', payment_setup['user'].id
        )
        assert pf1.batch_reference == 'PAY-2026-0001'
        assert pf2.batch_reference == 'PAY-2026-0002'

    def test_company_isolation(self, db, payment_setup):
        """Cannot add invoices from another company."""
        co2 = Company(name='OtherAB', org_number='9988776655', company_type='AB')
        db.session.add(co2)
        db.session.flush()

        ba2 = BankAccount(company_id=co2.id, bank_name='Nordea', account_number='999',
                          ledger_account='1930')
        db.session.add(ba2)
        db.session.commit()

        inv = payment_setup['inv_bg']
        pf, errors = create_payment_batch(
            co2.id, ba2.id, [inv.id], date(2026, 3, 1), 'pain001', payment_setup['user'].id
        )
        assert pf is None
        assert len(errors) > 0


# ---------------------------------------------------------------------------
# TestGeneratePain001
# ---------------------------------------------------------------------------

class TestGeneratePain001:
    def _create_batch(self, payment_setup, invoice_ids=None):
        co = payment_setup['company']
        ba = payment_setup['bank_account']
        if invoice_ids is None:
            invoice_ids = [payment_setup['inv_bg'].id, payment_setup['inv_iban'].id]
        pf, _ = create_payment_batch(
            co.id, ba.id, invoice_ids, date(2026, 3, 1), 'pain001', payment_setup['user'].id
        )
        return pf

    def test_generates_valid_xml(self, payment_setup):
        pf = self._create_batch(payment_setup)
        buf = generate_pain001_xml(pf.id)
        content = buf.read()
        assert b'<?xml' in content
        # Parse without error
        root = ET.fromstring(content)
        assert 'pain.001.001.03' in root.tag

    def test_domestic_bankgiro_structure(self, payment_setup):
        pf = self._create_batch(payment_setup, [payment_setup['inv_bg'].id])
        buf = generate_pain001_xml(pf.id)
        content = buf.read().decode('utf-8')
        assert 'BGNR' in content
        assert '1234567' in content  # bankgiro without dash

    def test_international_iban_structure(self, payment_setup):
        pf = self._create_batch(payment_setup, [payment_setup['inv_iban'].id])
        buf = generate_pain001_xml(pf.id)
        content = buf.read().decode('utf-8')
        assert 'IBAN' in content or 'DE89370400440532013000' in content
        assert 'COBADEFFXXX' in content

    def test_control_sum_matches(self, payment_setup):
        pf = self._create_batch(payment_setup)
        buf = generate_pain001_xml(pf.id)
        content = buf.read().decode('utf-8')
        # Total is 10000 + 5000 = 15000
        assert '15000.00' in content


# ---------------------------------------------------------------------------
# TestGenerateBankgirot
# ---------------------------------------------------------------------------

class TestGenerateBankgirot:
    def _create_batch(self, payment_setup):
        co = payment_setup['company']
        ba = payment_setup['bank_account']
        # Only BG and PG invoices work with bankgirot
        pf, _ = create_payment_batch(
            co.id, ba.id, [payment_setup['inv_bg'].id, payment_setup['inv_pg'].id],
            date(2026, 3, 1), 'bankgirot', payment_setup['user'].id
        )
        return pf

    def test_generates_fixed_width_file(self, payment_setup):
        pf = self._create_batch(payment_setup)
        buf = generate_bankgirot_file(pf.id)
        content = buf.read().decode('iso-8859-1')
        lines = content.rstrip('\n').split('\n')
        for line in lines:
            assert len(line) == 80, f'Line length {len(line)} != 80: {repr(line)}'

    def test_record_types_present(self, payment_setup):
        pf = self._create_batch(payment_setup)
        buf = generate_bankgirot_file(pf.id)
        content = buf.read().decode('iso-8859-1')
        lines = content.rstrip('\n').split('\n')
        types = {line[:2] for line in lines}
        assert '01' in types
        assert '20' in types
        assert '26' in types
        assert '09' in types

    def test_closing_record_totals(self, payment_setup):
        pf = self._create_batch(payment_setup)
        buf = generate_bankgirot_file(pf.id)
        content = buf.read().decode('iso-8859-1')
        lines = content.rstrip('\n').split('\n')
        closing = [l for l in lines if l.startswith('09')][0]
        # 2 payments (BG + PG)
        assert '00000002' in closing
        # Total: 10000 + 3000 = 13000 SEK = 1300000 öre
        assert '001300000' in closing


# ---------------------------------------------------------------------------
# TestBatchWorkflow
# ---------------------------------------------------------------------------

class TestBatchWorkflow:
    def test_generate_updates_status(self, app, payment_setup):
        co = payment_setup['company']
        ba = payment_setup['bank_account']
        pf, _ = create_payment_batch(
            co.id, ba.id, [payment_setup['inv_bg'].id],
            date(2026, 3, 1), 'pain001', payment_setup['user'].id
        )
        assert pf.status == 'draft'

        filepath = generate_payment_file(pf.id)
        assert filepath is not None
        pf_refreshed = _db.session.get(PaymentFile, pf.id)
        assert pf_refreshed.status == 'generated'
        assert pf_refreshed.file_path is not None

    def test_mark_uploaded_updates_status(self, app, payment_setup):
        co = payment_setup['company']
        ba = payment_setup['bank_account']
        pf, _ = create_payment_batch(
            co.id, ba.id, [payment_setup['inv_bg'].id],
            date(2026, 3, 1), 'pain001', payment_setup['user'].id
        )
        generate_payment_file(pf.id)
        result = mark_batch_uploaded(pf.id, payment_setup['user'].id)
        assert result is True
        pf_refreshed = _db.session.get(PaymentFile, pf.id)
        assert pf_refreshed.status == 'uploaded'

    def test_confirm_paid_marks_invoices(self, app, payment_setup):
        co = payment_setup['company']
        ba = payment_setup['bank_account']
        inv = payment_setup['inv_bg']
        pf, _ = create_payment_batch(
            co.id, ba.id, [inv.id],
            date(2026, 3, 1), 'pain001', payment_setup['user'].id
        )
        generate_payment_file(pf.id)
        mark_batch_uploaded(pf.id, payment_setup['user'].id)

        success, errors = confirm_batch_paid(pf.id, payment_setup['user'].id)
        assert success is True

        pf_refreshed = _db.session.get(PaymentFile, pf.id)
        assert pf_refreshed.status == 'confirmed'
        assert pf_refreshed.confirmed_at is not None

        inv_refreshed = _db.session.get(SupplierInvoice, inv.id)
        assert inv_refreshed.status == 'paid'
        assert inv_refreshed.paid_at is not None

    def test_cancel_batch(self, payment_setup):
        co = payment_setup['company']
        ba = payment_setup['bank_account']
        inv = payment_setup['inv_bg']
        pf, _ = create_payment_batch(
            co.id, ba.id, [inv.id],
            date(2026, 3, 1), 'pain001', payment_setup['user'].id
        )
        result = cancel_batch(pf.id, payment_setup['user'].id)
        assert result is True
        pf_refreshed = _db.session.get(PaymentFile, pf.id)
        assert pf_refreshed.status == 'cancelled'

        # Invoice should still be approved
        inv_refreshed = _db.session.get(SupplierInvoice, inv.id)
        assert inv_refreshed.status == 'approved'


# ---------------------------------------------------------------------------
# TestRoutes
# ---------------------------------------------------------------------------

class TestRoutes:
    def test_index_page_loads(self, db, logged_in_client, payment_setup):
        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = payment_setup['company'].id
        resp = logged_in_client.get('/payment-files/')
        assert resp.status_code == 200
        assert 'Betalningsfiler' in resp.data.decode()

    def test_new_batch_page_loads(self, db, logged_in_client, payment_setup):
        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = payment_setup['company'].id
        resp = logged_in_client.get('/payment-files/new')
        assert resp.status_code == 200
        assert 'Ny betalningsbatch' in resp.data.decode()

    def test_view_batch_page_loads(self, db, logged_in_client, payment_setup):
        co = payment_setup['company']
        ba = payment_setup['bank_account']
        pf, _ = create_payment_batch(
            co.id, ba.id, [payment_setup['inv_bg'].id],
            date(2026, 3, 1), 'pain001', payment_setup['user'].id
        )
        with logged_in_client.session_transaction() as sess:
            sess['active_company_id'] = co.id
        resp = logged_in_client.get(f'/payment-files/{pf.id}')
        assert resp.status_code == 200
        assert pf.batch_reference in resp.data.decode()
